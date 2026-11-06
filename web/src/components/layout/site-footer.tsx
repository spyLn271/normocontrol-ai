import { ShieldCheck } from "lucide-react";
import { getTranslations } from "next-intl/server";

export async function SiteFooter() {
  const t = await getTranslations("footer");
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-page flex-col gap-2 px-4 py-8 text-sm text-fg-muted sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-ok" aria-hidden />
          {t("privacy")}
        </p>
        <p>{t("note")}</p>
      </div>
    </footer>
  );
}
