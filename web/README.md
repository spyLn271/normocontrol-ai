# Normocontrol AI — веб-интерфейс

Next.js (App Router) + TypeScript, Tailwind CSS v4 с токенами Refero (стиль Dub), компоненты в стиле
shadcn/ui (Radix), графики Bklit UI (Gauge, Ring), TanStack Query, next-intl (`ru` — `/`, `kk` — `/kk`).
Подробности дизайна — [docs/FRONTEND.md](../docs/FRONTEND.md).

## Команды

```bash
corepack enable          # pnpm версии из package.json (packageManager)
pnpm install
pnpm dev                 # http://localhost:3000, API — на API_URL (по умолчанию http://localhost:8000)
pnpm dev:mock            # без бэкенда: моковые профили и отчёт; готовый отчёт — /checks/demo
pnpm lint && pnpm typecheck && pnpm test && pnpm format:check
pnpm build && pnpm start # production (output: standalone)
```

## Переменные окружения

| Переменная             | Когда       | Назначение                                                                                                  |
| ---------------------- | ----------- | ----------------------------------------------------------------------------------------------------------- |
| `API_URL`              | при запуске | адрес FastAPI; запросы `/api/*` проксирует `src/app/api/[...path]/route.ts` (тот же origin — CORS не нужен) |
| `NEXT_PUBLIC_API_MOCK` | при сборке  | `1` — мок-режим (`src/lib/api/mock.ts`, отчёт из `src/mocks/`)                                              |

## Docker

```bash
docker build -t normocontrol-web .
docker run -p 3000:3000 -e API_URL=http://api:8000 normocontrol-web
docker build --build-arg NEXT_PUBLIC_API_MOCK=1 -t normocontrol-web:demo .   # демо без бэкенда
```

## Структура

```
src/app/[locale]/        страницы: загрузка, /checks/[id], /profiles, /design (витрина токенов)
src/app/api/[...path]/   потоковый прокси к FastAPI
src/components/ui/       Button, Badge, Card, Select, Checkbox, … (только токены)
src/components/charts/   Bklit UI из реестра shadcn — не редактировать, обновлять:
                         pnpm dlx shadcn@4.21.4 add @bklit/gauge-chart @bklit/ring-chart --overwrite
src/components/report/   отчёт: ScoreGauge, CategoryRing, IssueCard, фильтры
src/lib/api/             zod-схемы контракта, клиент, ошибки, мок-режим
src/styles/tokens.css    дизайн-токены (+ тёмная тема по prefers-color-scheme)
messages/{ru,kk}.json    тексты интерфейса
```

## Заметки

- Графики рисуются только на клиенте (`useIsClient`): координаты SVG через `Math.sin/cos` в Node и
  браузере отличаются в последних знаках, и SSR-разметка не совпала бы при гидратации.
- Текст бейджей серьёзности — более тёмные оттенки (`*-fg`), чем цвета из FRONTEND.md: исходные пары
  не проходят WCAG AA (контраст 3.0–4.2). Обоснование и числа — в `src/styles/tokens.css`.
- Satoshi нет в Google Fonts, крупные заголовки — Inter 600. Шрифты скачиваются при сборке
  (`next/font`) и раздаются с нашего сервера.
