"use client";

import { useLocale, useTranslations } from "next-intl";
import { useTransition } from "react";
import { usePathname, useRouter } from "@/i18n/navigation";
import { type Locale, routing } from "@/i18n/routing";
import { cn } from "@/lib/utils";

const LABELS: Record<Locale, string> = { ru: "Рус", kk: "Қаз" };
const NAMES: Record<Locale, string> = { ru: "Русский", kk: "Қазақша" };

export function LocaleSwitcher() {
  const t = useTranslations("nav");
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  return (
    <div
      role="group"
      aria-label={t("language")}
      className="flex rounded-button border border-border p-0.5"
    >
      {routing.locales.map((item) => (
        <button
          key={item}
          type="button"
          lang={item}
          aria-label={NAMES[item]}
          aria-pressed={item === locale}
          disabled={pending}
          onClick={() => startTransition(() => router.replace(pathname, { locale: item }))}
          className={cn(
            "rounded-[6px] px-2.5 py-1 text-xs font-medium transition-colors",
            item === locale ? "bg-primary text-primary-fg" : "text-fg hover:bg-bg-subtle",
          )}
        >
          {LABELS[item]}
        </button>
      ))}
    </div>
  );
}
