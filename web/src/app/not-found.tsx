import Link from "next/link";

// Запросы вне локалей (до middleware) — минимальная страница без зависимостей от i18n.
export default function GlobalNotFound() {
  return (
    <html lang="ru">
      <body className="flex min-h-screen items-center justify-center p-6">
        <main className="text-center">
          <h1 className="text-xl font-semibold">404</h1>
          <p className="mt-2 text-sm text-fg-muted">Страница не найдена · Бет табылмады</p>
          <Link className="mt-4 inline-block text-accent underline" href="/">
            Normocontrol AI
          </Link>
        </main>
      </body>
    </html>
  );
}
