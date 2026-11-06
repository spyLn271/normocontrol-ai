# 006. API, очередь, хранение

Статус: принято (2026-10-25)

## Варианты

* **API:** FastAPI (выбран: pydantic-модели = контракт, OpenAPI из коробки), Litestar, DRF.
* **Очередь:** arq (выбран: asyncio — как и весь конвейер с LLM, Redis уже нужен), Celery
  (синхронный, тяжелее), RQ, Dramatiq.
* **БД:** не нужна на этапе MVP — отчёты живут ограниченное время (TTL в Redis).
  PostgreSQL появится вместе с аккаунтами (этап 6).

## Решение

* `POST /api/checks` (multipart: файл, профиль, `annotate`, `use_llm`) → 202 и статус;
  `GET /api/checks/{id}` — статус по шагам и отчёт; `GET /api/checks/{id}/annotated.docx`;
  `DELETE /api/checks/{id}` — удалить результаты досрочно; `GET /api/profiles[/{id}]`;
  `/healthz`, `/readyz`, `/metrics` (Prometheus).
* Проверки на входе: расширение и тип, размер (`api.max_upload_mb`, ещё до чтения тела — по
  Content-Length), структура архива (zip-бомбы), существование профиля.
* id проверки — `secrets.token_urlsafe(18)`: ссылка на отчёт — это и есть доступ.
* Очередь: `jobs.backend: arq` (продакшен) или `inline` (разработка). Ограничения:
  `max_concurrency` на процесс, `max_pending` (503 «очередь заполнена»), `timeout_s`.
* Исходный файл удаляется в момент начала обработки (`pop_upload`), задача не
  перезапускается (`max_tries = 1`), отчёт и `.docx` с комментариями — до `result_ttl_s`.
* Redis без персистентности (`--save "" --appendonly no`): документы не пишутся на диск.
* Ответы с отчётами — `Cache-Control: no-store`; заголовки безопасности; X-Request-ID;
  в логах нет текста документов и имён файлов.

## Последствия

Масштабирование — числом воркеров (`NC_WORKERS`). Метрики HTTP и проверок — в `/metrics`.
Для нескольких процессов uvicorn в одном контейнере нужен multiprocess-режим
prometheus_client — поэтому рекомендуем 1 процесс на контейнер и масштабировать контейнеры.
