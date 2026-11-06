"""CLI: ``normocontrol parse | check | profiles | dataset | eval | rag | serve | worker``."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from normocontrol import __version__
from normocontrol.config.settings import Settings, get_settings
from normocontrol.logs import configure_logging

app = typer.Typer(
    name="normocontrol",
    help="Normocontrol AI — проверка оформления документов по требованиям РК.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,  # в локальных переменных может быть текст документа
)
profiles_app = typer.Typer(help="Профили требований.", no_args_is_help=True)
dataset_app = typer.Typer(help="Тестовые документы (fixtures).", no_args_is_help=True)
rag_app = typer.Typer(help="База знаний по стандартам (RAG).", no_args_is_help=True)
app.add_typer(profiles_app, name="profiles")
app.add_typer(dataset_app, name="dataset")
app.add_typer(rag_app, name="rag")

console = Console()
err = Console(stderr=True)


def _settings() -> Settings:
    settings = get_settings()
    configure_logging(settings.log)
    return settings


def _version(value: bool) -> None:
    if value:
        console.print(f"normocontrol {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version, is_eager=True, help="Показать версию."),
    ] = False,
) -> None:
    del version


# ---------------------------------------------------------------------- parse / check


@app.command()
def parse(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Файл .docx")],
    output: Annotated[
        Path | None, typer.Option("-o", "--output", help="Куда сохранить JSON")
    ] = None,
    pages: Annotated[bool, typer.Option(help="Оценить номера страниц через LibreOffice")] = True,
) -> None:
    """Разобрать .docx во внутреннюю модель документа (JSON)."""
    from normocontrol.parser.docx_parser import parse_docx  # noqa: PLC0415
    from normocontrol.parser.pages import LibreOfficePageEstimator  # noqa: PLC0415
    from normocontrol.parser.safety import InvalidDocumentError  # noqa: PLC0415

    settings = _settings()
    estimator = None
    if pages and settings.pages.mode != "off":
        candidate = LibreOfficePageEstimator(settings.pages.soffice_path, settings.pages.timeout_s)
        estimator = candidate if candidate.available() else None
    try:
        document = parse_docx(file, page_estimator=estimator)
    except InvalidDocumentError as exc:
        err.print(f"[red]Ошибка:[/red] {exc}")
        raise typer.Exit(2) from exc
    payload = document.model_dump_json(indent=2)
    if output:
        output.write_text(payload, encoding="utf-8")
        console.print(f"Модель документа сохранена: {output} ({document.stats.paragraphs} абзацев)")
    else:
        sys.stdout.write(payload + "\n")


@app.command()
def check(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False, help="Файл .docx")],
    profile: Annotated[str | None, typer.Option("-p", "--profile", help="ID профиля")] = None,
    output_format: Annotated[
        str, typer.Option("--format", "-f", help="console | json")
    ] = "console",
    output: Annotated[
        Path | None, typer.Option("-o", "--output", help="Сохранить отчёт JSON")
    ] = None,
    annotate: Annotated[
        Path | None, typer.Option("--annotate", help="Сохранить .docx с комментариями")
    ] = None,
    llm: Annotated[bool | None, typer.Option("--llm/--no-llm", help="ИИ-проверки")] = None,
    fail_on: Annotated[
        str, typer.Option(help="Код выхода 1 при ошибках уровня: error | warning | never")
    ] = "error",
) -> None:
    """Проверить документ по профилю и вывести отчёт."""
    from normocontrol.parser.safety import InvalidDocumentError  # noqa: PLC0415
    from normocontrol.pipeline import CheckOptions, Services, run_check_sync  # noqa: PLC0415
    from normocontrol.profiles.loader import ProfileError  # noqa: PLC0415
    from normocontrol.report.render_console import render_console  # noqa: PLC0415

    settings = _settings()
    if output_format not in {"console", "json"}:
        raise typer.BadParameter("--format: console или json")
    try:
        services = Services.from_settings(settings)
        outcome = run_check_sync(
            file.read_bytes(),
            CheckOptions(
                profile_id=profile or settings.default_profile,
                filename=file.name,
                use_llm=llm,
                annotate=annotate is not None,
            ),
            services,
        )
    except (InvalidDocumentError, ProfileError) as exc:
        err.print(f"[red]Ошибка:[/red] {exc}")
        raise typer.Exit(2) from exc

    report = outcome.report
    payload = report.model_dump_json(indent=2)
    if output:
        output.write_text(payload, encoding="utf-8")
    if annotate and outcome.annotated:
        annotate.write_bytes(outcome.annotated)
    if output_format == "json":
        sys.stdout.write(payload + "\n")
    else:
        render_console(report, console)
        if output:
            console.print(f"[dim]Отчёт JSON: {output}[/dim]")
        if annotate:
            console.print(f"[dim]Документ с комментариями: {annotate}[/dim]")

    severities = {"error": {"error"}, "warning": {"error", "warning"}, "never": set()}
    blocking = severities.get(fail_on, {"error"})
    if any(issue.severity.value in blocking for issue in report.issues):
        raise typer.Exit(1)


# ---------------------------------------------------------------------- profiles


@profiles_app.command("list")
def profiles_list() -> None:
    """Список профилей."""
    from normocontrol.profiles.loader import ProfileRegistry  # noqa: PLC0415

    registry = ProfileRegistry.from_directory(_settings().profiles_dir)
    table = Table("id", "Название", "Статус", "Типы документов")
    for item in registry:
        table.add_row(item.id, item.title, item.status.value, ", ".join(item.doc_types))
    console.print(table)


@profiles_app.command("show")
def profiles_show(profile_id: str) -> None:
    """Профиль с учётом наследования (extends), в YAML."""
    import yaml  # noqa: PLC0415

    from normocontrol.profiles.loader import ProfileError, ProfileRegistry  # noqa: PLC0415

    registry = ProfileRegistry.from_directory(_settings().profiles_dir)
    try:
        data = registry.get(profile_id).model_dump(mode="json", exclude_none=True)
    except ProfileError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    sys.stdout.write(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


@profiles_app.command("validate")
def profiles_validate(
    directory: Annotated[Path | None, typer.Argument(help="Каталог профилей")] = None,
) -> None:
    """Проверить все профили каталога."""
    from normocontrol.profiles.loader import ProfileError, ProfileRegistry  # noqa: PLC0415

    try:
        registry = ProfileRegistry.from_directory(directory or _settings().profiles_dir)
    except ProfileError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc
    failed = False
    for profile_id, problem in registry.validate_all().items():
        if problem:
            failed = True
            err.print(f"[red]✗[/red] {problem}")
        else:
            console.print(f"[green]✓[/green] {profile_id}")
    if failed:
        raise typer.Exit(1)


# ---------------------------------------------------------------------- dataset / eval


@dataset_app.command("generate")
def dataset_generate(
    out: Annotated[Path, typer.Option("--out", help="Каталог датасета")] = Path(
        "tests/fixtures/generated"
    ),
    profile: Annotated[list[str] | None, typer.Option("--profile", "-p")] = None,
    count: Annotated[int, typer.Option(min=1, help="Документов на профиль")] = 100,
    seed: Annotated[int, typer.Option(help="Seed — генерация повторяется")] = 42,
) -> None:
    """Сгенерировать правильные документы и документы с известными ошибками."""
    from normocontrol.dataset.generate import generate_dataset  # noqa: PLC0415
    from normocontrol.profiles.loader import ProfileRegistry  # noqa: PLC0415

    registry = ProfileRegistry.from_directory(_settings().profiles_dir)
    profiles = profile or [p.id for p in registry.selectable()]
    samples = generate_dataset(registry, out, profiles=profiles, count=count, seed=seed)
    console.print(f"Сгенерировано документов: {len(samples)} → {out}")


@app.command("eval")
def evaluate(
    directory: Annotated[Path, typer.Argument(exists=True, file_okay=False)] = Path(
        "tests/fixtures/generated"
    ),
    out: Annotated[Path | None, typer.Option("--out", help="Сохранить таблицу Markdown")] = None,
    min_precision: Annotated[float, typer.Option(help="Порог для кода выхода")] = 0.0,
) -> None:
    """Precision / recall правил на размеченном датасете."""
    from normocontrol.evaluation.evaluate import evaluate_directory, to_markdown  # noqa: PLC0415
    from normocontrol.profiles.loader import ProfileRegistry  # noqa: PLC0415

    registry = ProfileRegistry.from_directory(_settings().profiles_dir)
    result = evaluate_directory(directory, registry)
    table = Table("rule_id", "precision", "recall", "TP", "FP", "FN")
    for rule_id in sorted(result.rules):
        score = result.rules[rule_id]
        table.add_row(
            rule_id,
            f"{score.precision:.3f}",
            f"{score.recall:.3f}",
            str(score.tp),
            str(score.fp),
            str(score.fn),
        )
    total = result.total
    table.add_row(
        "[bold]итого[/bold]",
        f"[bold]{total.precision:.3f}[/bold]",
        f"[bold]{total.recall:.3f}[/bold]",
        str(total.tp),
        str(total.fp),
        str(total.fn),
    )
    console.print(table)
    console.print(f"Документов: {result.documents}")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(to_markdown(result), encoding="utf-8")
        console.print(f"Таблица сохранена: {out}")
    if total.precision < min_precision:
        raise typer.Exit(1)


# ---------------------------------------------------------------------- rag


@rag_app.command("index")
def rag_index(
    file: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    source: Annotated[str, typer.Option(help="Имя источника, как в profile.rag_sources")],
    source_id: Annotated[str, typer.Option(help="Стабильный id источника (slug)")],
) -> None:
    """Проиндексировать один стандарт / методичку."""
    from normocontrol.rag.embeddings import create_embedder  # noqa: PLC0415
    from normocontrol.rag.indexer import index_file  # noqa: PLC0415
    from normocontrol.rag.store import QdrantStore  # noqa: PLC0415

    settings = _settings()

    async def run() -> int:
        embedder = create_embedder(settings.embeddings)
        store = QdrantStore.from_settings(settings.vector_store)
        try:
            result = await index_file(
                file,
                source=source,
                source_id=source_id,
                embedder=embedder,
                store=store,
                max_tokens=settings.rag.max_chunk_tokens,
                overlap_tokens=settings.rag.chunk_overlap_tokens,
            )
        finally:
            await embedder.aclose()
            await store.aclose()
        return result.chunks

    console.print(f"Проиндексировано чанков: {asyncio.run(run())}")


@rag_app.command("index-registry")
def rag_index_registry(
    registry: Annotated[Path, typer.Argument(exists=True, dir_okay=False)] = Path(
        "research/sources.yaml"
    ),
    base_dir: Annotated[Path, typer.Option(help="Корень для local_file")] = Path(),
) -> None:
    """Проиндексировать все источники реестра, у которых есть local_file и rag_source."""
    from normocontrol.rag.embeddings import create_embedder  # noqa: PLC0415
    from normocontrol.rag.indexer import index_registry  # noqa: PLC0415
    from normocontrol.rag.store import QdrantStore  # noqa: PLC0415

    settings = _settings()

    async def run() -> list[tuple[str, int, str | None]]:
        embedder = create_embedder(settings.embeddings)
        store = QdrantStore.from_settings(settings.vector_store)
        try:
            results = await index_registry(
                registry,
                base_dir=base_dir,
                embedder=embedder,
                store=store,
                max_tokens=settings.rag.max_chunk_tokens,
                overlap_tokens=settings.rag.chunk_overlap_tokens,
            )
        finally:
            await embedder.aclose()
            await store.aclose()
        return [(r.source, r.chunks, r.error) for r in results]

    failed = False
    for source, chunks, error in asyncio.run(run()):
        if error:
            failed = True
            err.print(f"[red]✗[/red] {source}: {error}")
        else:
            console.print(f"[green]✓[/green] {source}: {chunks} чанков")
    if failed:
        raise typer.Exit(1)


@rag_app.command("search")
def rag_search(
    query: str,
    profile: Annotated[str | None, typer.Option("-p", "--profile")] = None,
    k: Annotated[int, typer.Option("-k", "--k", min=1, max=20)] = 5,
) -> None:
    """Найти пункты стандартов по запросу (с фильтром по источникам профиля)."""
    from normocontrol.pipeline import Services  # noqa: PLC0415

    settings = _settings()
    services = Services.from_settings(settings)
    if services.retriever is None:
        err.print("[red]RAG выключен (llm.enabled / rag.enabled)[/red]")
        raise typer.Exit(2)
    sources = services.profiles.get(profile).rag_sources if profile else []

    async def run() -> None:
        assert services.retriever is not None  # noqa: S101
        try:
            chunks = await services.retriever.retrieve(query, sources=sources, k=k)
        finally:
            await services.aclose()
        for chunk in chunks:
            console.print(f"[bold]{chunk.citation}[/bold] [dim]{chunk.score:.3f}[/dim]")
            console.print(chunk.text[:500] + ("…" if len(chunk.text) > 500 else ""))
            console.print()

    asyncio.run(run())


@rag_app.command("eval")
def rag_eval(
    questions: Annotated[Path, typer.Argument(exists=True, dir_okay=False)] = Path(
        "tests/rag/questions.yaml"
    ),
    k: Annotated[int, typer.Option("-k", "--k", min=1, max=20)] = 5,
) -> None:
    """Hit@k и MRR поиска по набору вопросов."""
    from normocontrol.pipeline import Services  # noqa: PLC0415
    from normocontrol.rag.evaluate import evaluate_retrieval, load_questions  # noqa: PLC0415

    settings = _settings()
    services = Services.from_settings(settings)
    if services.retriever is None:
        err.print("[red]RAG выключен[/red]")
        raise typer.Exit(2)

    async def run() -> None:
        assert services.retriever is not None  # noqa: S101
        try:
            result = await evaluate_retrieval(services.retriever, load_questions(questions), k=k)
        finally:
            await services.aclose()
        console.print(
            f"Вопросов: {result.questions} · Hit@{k}: {result.hit_rate:.3f} · MRR: {result.mrr:.3f}"
        )
        for miss in result.misses:
            console.print(f"[yellow]промах:[/yellow] {miss}")

    asyncio.run(run())


@rag_app.command("stats")
def rag_stats() -> None:
    """Сколько чанков каждого источника в векторной БД."""
    from normocontrol.rag.store import QdrantStore  # noqa: PLC0415

    settings = _settings()

    async def run() -> dict[str, int]:
        store = QdrantStore.from_settings(settings.vector_store)
        try:
            return await store.sources()
        finally:
            await store.aclose()

    stats = asyncio.run(run())
    if not stats:
        console.print("База знаний пуста. Загрузите стандарты: normocontrol rag index-registry")
    for source, count in sorted(stats.items()):
        console.print(f"{source}: {count}")


# ---------------------------------------------------------------------- serve / worker


@app.command()
def serve(
    host: Annotated[str | None, typer.Option()] = None,
    port: Annotated[int | None, typer.Option()] = None,
    reload: Annotated[bool, typer.Option(help="Перезапуск при изменении кода")] = False,
) -> None:
    """Запустить HTTP API (uvicorn)."""
    import uvicorn  # noqa: PLC0415

    settings = _settings()
    uvicorn.run(
        "normocontrol.api.app:create_app",
        factory=True,
        host=host or settings.api.host,
        port=port or settings.api.port,
        workers=None if reload else settings.api.workers,
        reload=reload,
        root_path=settings.api.root_path,
        log_config=None,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


@app.command()
def worker() -> None:
    """Запустить воркер очереди проверок (arq + Redis)."""
    from arq import run_worker  # noqa: PLC0415

    from normocontrol.api.worker import WorkerSettings  # noqa: PLC0415

    _settings()
    run_worker(WorkerSettings)  # type: ignore[arg-type]  # arq ожидает свой Protocol
