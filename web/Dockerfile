# syntax=docker/dockerfile:1.7
# Normocontrol AI — веб-интерфейс (Next.js standalone).
#   docker build -t normocontrol-web ./web
#   docker run -p 3000:3000 -e API_URL=http://api:8000 normocontrol-web
# API_URL читается при запуске (Route Handler /api/*), поэтому образ один для всех окружений.

ARG NODE_IMAGE=node:22.23.3-alpine

FROM ${NODE_IMAGE} AS base
ENV NEXT_TELEMETRY_DISABLED=1 \
    COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /app

FROM base AS deps
COPY package.json pnpm-lock.yaml .npmrc ./
RUN --mount=type=cache,id=pnpm-store,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM base AS build
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# 1 — собрать демо-версию на моковых данных (без бэкенда)
ARG NEXT_PUBLIC_API_MOCK=0
ENV NEXT_PUBLIC_API_MOCK=${NEXT_PUBLIC_API_MOCK}
RUN pnpm build

FROM ${NODE_IMAGE} AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    API_URL=http://api:8000
RUN addgroup -S -g 1001 nodejs && adduser -S -u 1001 -G nodejs nextjs
COPY --from=build --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=build --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=build --chown=nextjs:nodejs /app/public ./public
USER nextjs
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1:3000/ || exit 1
CMD ["node", "server.js"]
