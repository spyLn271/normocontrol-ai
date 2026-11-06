import { notFound } from "next/navigation";

// Любой неизвестный путь внутри локали → локализованная 404 ([locale]/not-found.tsx)
export default function CatchAll() {
  notFound();
}
