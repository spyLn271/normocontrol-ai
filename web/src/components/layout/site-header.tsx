import { getTranslations } from "next-intl/server";
import { LocaleSwitcher } from "@/components/layout/locale-switcher";
import { NavLink } from "@/components/layout/nav-link";
import { Link } from "@/i18n/navigation";

export async function SiteHeader() {
  const t = await getTranslations("nav");
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-page items-center gap-4 px-4 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold text-fg"
          aria-label={t("home")}
        >
          <span
            aria-hidden
            className="flex size-7 items-center justify-center rounded-button bg-primary font-mono text-xs text-primary-fg"
          >
            NC
          </span>
          <span className="hidden sm:inline">Normocontrol AI</span>
        </Link>
        <nav aria-label="primary" className="flex items-center gap-1 text-sm">
          <NavLink href="/">{t("check")}</NavLink>
          <NavLink href="/profiles">{t("profiles")}</NavLink>
        </nav>
        <div className="ml-auto">
          <LocaleSwitcher />
        </div>
      </div>
    </header>
  );
}
