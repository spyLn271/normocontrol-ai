import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";

export default function NotFound() {
  const t = useTranslations("errors");
  return (
    <section className="mx-auto flex max-w-lg flex-col items-center gap-3 py-12 text-center">
      <p className="font-mono text-sm text-fg-muted">404</p>
      <h1 className="text-2xl font-semibold text-fg">{t("notFoundTitle")}</h1>
      <p className="text-sm text-fg-muted">{t("notFoundText")}</p>
      <Button asChild className="mt-2">
        <Link href="/">{t("home")}</Link>
      </Button>
    </section>
  );
}
