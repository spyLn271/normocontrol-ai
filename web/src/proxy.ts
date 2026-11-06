import createMiddleware from "next-intl/middleware";
import { routing } from "./i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Всё, кроме API, служебных путей Next.js и файлов с расширением
  matcher: "/((?!api|_next|_vercel|.*\\..*).*)",
};
