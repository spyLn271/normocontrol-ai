"use client";

import { AlertCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Link } from "@/i18n/navigation";

interface ErrorStateProps {
  title: string;
  text: string;
  onRetry?: () => void;
}

export function ErrorState({ title, text, onRetry }: ErrorStateProps) {
  const t = useTranslations();
  return (
    <section
      role="alert"
      className="mx-auto flex max-w-lg flex-col items-center gap-3 rounded-card-lg border border-border px-6 py-12 text-center"
    >
      <AlertCircle className="size-8 text-error" aria-hidden />
      <h1 className="text-xl font-semibold text-fg">{title}</h1>
      <p className="text-sm text-fg-muted">{text}</p>
      <div className="mt-2 flex flex-wrap justify-center gap-2">
        {onRetry && (
          <Button variant="secondary" onClick={onRetry}>
            {t("errors.retry")}
          </Button>
        )}
        <Button asChild>
          <Link href="/">{t("check.newCheck")}</Link>
        </Button>
      </div>
    </section>
  );
}
