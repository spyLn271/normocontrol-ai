.PHONY: install lint format typecheck test test-all eval dataset serve worker web up down index check

install:            ## зависимости (бэкенд + extra pdf) и pre-commit
	uv sync --extra pdf
	uv run pre-commit install

lint:               ## ruff: линтер и проверка форматирования
	uv run ruff check .
	uv run ruff format --check .

format:             ## автоисправление и форматирование
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy

test:               ## быстрые тесты (без LLM; интеграция с Redis — если есть redis-server)
	uv run pytest -m "not llm" --cov

test-all:           ## включая тесты с настоящей Ollama
	uv run pytest -m "" --cov

dataset:            ## 100 документов на профиль с известными ошибками
	uv run normocontrol dataset generate --out tests/fixtures/generated --count 100

eval: dataset       ## precision / recall правил → docs/benchmarks
	uv run normocontrol eval tests/fixtures/generated --out docs/benchmarks/$$(date +%F)-rules.md

serve:
	uv run normocontrol serve --reload

worker:
	uv run normocontrol worker

web:
	cd web && pnpm dev

up:                 ## весь стек в Docker
	docker compose up -d --build

down:
	docker compose down

index:              ## загрузить стандарты из research/sources.yaml в базу знаний
	uv run normocontrol rag index-registry research/sources.yaml

check:              ## всё, что проверяет CI
	$(MAKE) lint typecheck test
