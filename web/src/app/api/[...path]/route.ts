/**
 * Прокси /api/* → FastAPI. Адрес бэкенда читается во время работы (API_URL), а не при сборке,
 * поэтому один Docker-образ подходит для любого окружения. Тело запроса передаётся потоком:
 * загрузка .docx до 20 МБ не буферизуется в памяти Next.js. CORS не нужен — тот же origin.
 */
import { type NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const UPSTREAM_TIMEOUT_MS = 120_000;
// Заголовки соединения и те, что Node fetch пересчитывает сам (тело уже распаковано)
const SKIP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
  "content-encoding",
  "cookie",
  "set-cookie",
]);

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

function apiBaseUrl(): string {
  return (process.env.API_URL ?? "http://localhost:8000").replace(/\/+$/, "");
}

function copyHeaders(source: Headers): Headers {
  const result = new Headers();
  source.forEach((value, key) => {
    if (!SKIP_HEADERS.has(key.toLowerCase())) result.set(key, value);
  });
  return result;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  const target = new URL(`${apiBaseUrl()}/api/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;

  const headers = copyHeaders(request.headers);
  const forwardedFor = request.headers.get("x-forwarded-for");
  if (forwardedFor) headers.set("x-forwarded-for", forwardedFor);
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));
  const host = request.headers.get("host");
  if (host) headers.set("x-forwarded-host", host);

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers,
    redirect: "manual",
    cache: "no-store",
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    ...(hasBody ? { body: request.body, duplex: "half" } : {}),
  };

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    return Response.json(
      {
        error: {
          code: "upstream_unavailable",
          message: "Сервис проверки временно недоступен. Попробуйте позже.",
        },
      },
      { status: 502 },
    );
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: copyHeaders(upstream.headers),
  });
}

export { proxy as DELETE, proxy as GET, proxy as HEAD, proxy as POST };
