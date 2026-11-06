import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  locales: ["ru", "kk"],
  defaultLocale: "ru",
  // Префикс у обеих локалей (/ru/…, /kk/…): «/» перенаправляется по cookie / Accept-Language.
  // Вариант "as-needed" требует внутреннего rewrite, который в standalone-сборке Next 16.4
  // зацикливается (307 → тот же адрес), поэтому — только редиректы, без rewrite.
  localePrefix: "always",
});

export type Locale = (typeof routing.locales)[number];
