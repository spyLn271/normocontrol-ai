import { type ReactNode } from "react";
import "./globals.css";

// Корневой layout — «прозрачный»: <html> рендерит [locale]/layout.tsx (next-intl, lang по локали).
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
