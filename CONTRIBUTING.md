# Как мы работаем

Команда из двух человек: **ментор** и **разработчик**.

## Роли

**Ментор**
- держит видение продукта и приоритеты (VISION, ROADMAP);
- формулирует задачи в Issues с критериями готовности;
- делает code review каждого PR в течение 1–2 дней;
- проводит еженедельный созвон и демо по итогам этапа.

**Разработчик**
- берёт задачи из Issues, предлагает техническое решение;
- если задача непонятна или больше 2–3 дней работы — пишет в Issue и разбивает её;
- обновляет docs, если решение меняет архитектуру.

## Процесс

1. **Issue** → у каждой задачи есть описание, критерии готовности и метка этапа (`stage-1`, `stage-2`…).
2. **Ветка** от `main`: `feat/parser-styles`, `fix/margins-tolerance`, `docs/rules`.
3. **Pull Request** в `main`:
   - ссылка на Issue (`Closes #12`);
   - что сделано и как проверить;
   - тесты проходят в CI.
4. **Review** ментора → правки → merge (squash).
5. Прямые коммиты в `main` — нельзя (включить branch protection).

## Коммиты

[Conventional Commits](https://www.conventionalcommits.org/ru/):
```
feat(parser): resolve style inheritance for runs
fix(rules): margins tolerance in cm
docs: add bibliography rules
```

## Ритм

- **Еженедельно** — созвон 30–45 мин: что сделано, что мешает, план на неделю.
- **Асинхронно** — вопросы в Issues/PR, а не в личке, чтобы решения не терялись.
- **Конец этапа** — демо по ROADMAP.

## Команды разработчика

```bash
make install    # uv sync --extra pdf + pre-commit install
make check      # ruff check · ruff format --check · mypy --strict · pytest (как в CI)
make eval       # датасет 100 документов на профиль → docs/benchmarks/<дата>-rules.md
uv run pytest -m llm          # тесты с настоящей Ollama (в CI не запускаются)
```

CI (`.github/workflows/ci.yml`) блокирует merge, если не проходит линтер, типы, тесты
(включая интеграцию с Redis/arq), сборка фронтенда или precision правил на датасете < 0.95.

## Важные архитектурные решения

Записываем в `docs/adr/NNN-название.md` (Architecture Decision Record): контекст, решение, альтернативы, последствия.

## Данные

- Реальные документы в репозиторий — **только обезличенные** (без ФИО, номеров, подписей).
- Никаких API-ключей в коде: `.env` (в `.gitignore`), пример — `.env.example`.
