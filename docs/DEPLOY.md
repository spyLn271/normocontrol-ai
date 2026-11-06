# Развёртывание

## Состав

| Сервис | Образ | Назначение |
|---|---|---|
| `api` | `normocontrol/api` (`Dockerfile`) | HTTP API, приём файлов, статусы и отчёты |
| `worker` | тот же образ, команда `worker` | обработка очереди: парсинг, правила, LLM, отчёт |
| `web` | `normocontrol/web` (`web/Dockerfile`) | веб-интерфейс; `/api/*` проксируется в `api` |
| `redis` | `redis:7.4.10-alpine` | очередь arq, статусы, временные файлы (TTL, без записи на диск) |
| `qdrant` | `qdrant/qdrant:v1.19.2-unprivileged` | векторная база стандартов |
| `ollama` | `ollama/ollama:0.40.2` | LLM и эмбеддинги |
| `ollama-init` | тот же | одноразово скачивает модели |
| `indexer` | `normocontrol/api` (профиль `tools`) | загружает стандарты из `research/sources.yaml` в Qdrant |

## Первый запуск

```bash
cp .env.example .env                    # при необходимости: NC_LLM__MODEL, порты
docker compose up -d --build
docker compose logs -f ollama-init      # дождаться загрузки моделей (qwen3:8b ≈ 5 ГБ)
# положить тексты стандартов в ./data/standards (см. research/sources.yaml)
docker compose --profile tools run --rm indexer
curl http://localhost:8000/readyz
```

Порты: `NC_API_PORT` (8000), `NC_WEB_PORT` (3000). Наружу публикуйте только веб
через обратный прокси с TLS (nginx / Caddy); API доступен вебу по внутренней сети.

## GPU

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Нужен nvidia-container-toolkit. Ориентиры памяти — docs/GUIDE.md, раздел 4.3; модель по
умолчанию `qwen3:8b` (≈ 5 ГБ VRAM). Для большой нагрузки — vLLM вместо Ollama:
`NC_LLM__PROVIDER=openai_compatible`, `NC_LLM__BASE_URL=http://vllm:8000`.

## Масштабирование

* **Воркеры:** `NC_WORKERS=4 docker compose up -d` — каждый обрабатывает
  `NC_JOBS__MAX_CONCURRENCY` проверок одновременно.
* **Защита от перегрузки:** `NC_JOBS__MAX_PENDING` — при заполненной очереди API отвечает 503.
* **LLM:** `OLLAMA_NUM_PARALLEL` и `NC_LLM__MAX_CONCURRENCY` должны соответствовать VRAM.
* **API:** 1 процесс uvicorn на контейнер (метрики Prometheus без multiprocess-режима),
  масштабируйте числом контейнеров за балансировщиком.

## Конфигурация

Все параметры — `config.yaml` + переменные `NC_<РАЗДЕЛ>__<КЛЮЧ>` (см. `.env.example`).
В образе включены `NC_ENV=prod` и JSON-логи (`NC_LOG__JSON_FORMAT=true`).

## Наблюдаемость

* `GET /healthz` — liveness, `GET /readyz` — Redis, очередь, LLM (503, если недоступно критичное).
* `GET /metrics` — `normocontrol_checks_total`, `normocontrol_check_duration_seconds`,
  `normocontrol_checks_in_progress`, `normocontrol_issues_total`,
  `normocontrol_http_request_duration_seconds`.
* Каждый ответ содержит `X-Request-ID`; тот же id — в JSON-логах.

## Персональные данные

* Файл живёт в Redis только до начала обработки и удаляется воркером.
* Отчёт и `.docx` с комментариями — `NC_JOBS__RESULT_TTL_S` (по умолчанию 1 час),
  пользователь может удалить их раньше (`DELETE /api/checks/{id}`).
* Redis запущен без RDB/AOF — данные не попадают на диск.
* В логах нет текста документов и имён файлов; логи промптов LLM (`NC_LLM__LOG_DIR`)
  выключены по умолчанию.
* Контейнеры `api`/`worker`: непривилегированный пользователь, read-only файловая система,
  `no-new-privileges`.
* Ссылка на отчёт содержит непредсказуемый id (144 бита) — не публикуйте её.

## Обновление

```bash
git pull
docker compose build api web
docker compose up -d
```

Смена модели эмбеддингов требует переиндексации: `docker compose --profile tools run --rm indexer`.
