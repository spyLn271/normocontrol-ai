import { type Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { type ReactNode } from "react";
import { CheckerBadge, SeverityBadge } from "@/components/report/badges";
import { CategoryRing } from "@/components/report/category-ring";
import { ScoreGauge } from "@/components/report/score-gauge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

interface PageProps {
  params: Promise<{ locale: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "design" });
  return { title: t("title"), robots: { index: false, follow: false } };
}

const COLORS = [
  ["bg", "bg-bg"],
  ["bg-subtle", "bg-bg-subtle"],
  ["border", "bg-border"],
  ["fg", "bg-fg"],
  ["fg-muted", "bg-fg-muted"],
  ["accent", "bg-accent"],
  ["primary", "bg-primary"],
] as const;

const SEVERITY_SWATCHES = [
  ["error", "bg-error", "bg-error-subtle text-error-fg"],
  ["warning", "bg-warning", "bg-warning-subtle text-warning-fg"],
  ["info", "bg-info", "bg-info-subtle text-info-fg"],
  ["ok", "bg-ok", "bg-ok-subtle text-ok-fg"],
] as const;

const RADII = [
  ["badge 9999px", "rounded-badge"],
  ["button 8px", "rounded-button"],
  ["card 12px", "rounded-card"],
  ["card-lg 16px", "rounded-card-lg"],
  ["input 6px", "rounded-input"],
] as const;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-fg">{title}</h2>
      {children}
    </section>
  );
}

export default async function DesignPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("design");

  return (
    <div className="flex flex-col gap-section">
      <header className="flex flex-col gap-2">
        <h1 className="font-display text-4xl font-semibold tracking-tight text-fg">{t("title")}</h1>
        <p className="text-fg-muted">{t("subtitle")}</p>
      </header>

      <Section title={t("colors")}>
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-7">
          {COLORS.map(([name, className]) => (
            <li key={name} className="flex flex-col gap-2">
              <span className={`h-14 rounded-card border border-border ${className}`} />
              <span className="font-mono text-xs text-fg">{name}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title={t("severity")}>
        <ul className="grid gap-3 sm:grid-cols-4">
          {SEVERITY_SWATCHES.map(([name, solid, subtle]) => (
            <li key={name} className="flex flex-col gap-2 rounded-card border border-border p-3">
              <span className={`h-8 rounded-input ${solid}`} />
              <span
                className={`rounded-badge px-2.5 py-0.5 text-center text-xs font-medium ${subtle}`}
              >
                {name}
              </span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title={t("typography")}>
        <div className="flex flex-col gap-2">
          <p className="font-display text-5xl font-semibold tracking-tight text-fg">
            Normocontrol AI
          </p>
          <p className="text-2xl font-semibold text-fg">{t("sample")}</p>
          <p className="text-base text-fg">{t("sample")}</p>
          <p className="text-sm text-fg-muted">{t("sample")}</p>
          <p className="font-mono text-sm text-fg">page.margins · p-42 · 1,25 см</p>
        </div>
      </Section>

      <Section title={t("buttons")}>
        <div className="flex flex-wrap gap-3">
          <Button>{t("primary")}</Button>
          <Button variant="secondary">{t("secondary")}</Button>
          <Button variant="ghost">{t("ghost")}</Button>
          <Button variant="danger">Delete</Button>
          <Button variant="link">Link</Button>
          <Button disabled>{t("disabled")}</Button>
        </div>
      </Section>

      <Section title={t("badges")}>
        <div className="flex flex-wrap gap-2">
          <SeverityBadge severity="error" />
          <SeverityBadge severity="warning" />
          <SeverityBadge severity="info" />
          <Badge tone="ok">ok</Badge>
          <Badge tone="accent">accent</Badge>
          <Badge tone="outline">outline</Badge>
          <CheckerBadge checker="rule" />
          <CheckerBadge checker="structure" />
          <CheckerBadge checker="llm" />
        </div>
      </Section>

      <Section title={t("inputs")}>
        <div className="grid max-w-md gap-3">
          <Input placeholder={t("inputPlaceholder")} aria-label={t("inputPlaceholder")} />
          <Input
            placeholder={t("inputPlaceholder")}
            aria-label={t("inputPlaceholder")}
            aria-invalid
          />
          <Alert tone="info">{t("cardText")}</Alert>
          <Alert tone="warning">{t("cardText")}</Alert>
        </div>
      </Section>

      <Section title={t("cards")}>
        <div className="grid gap-4 sm:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>{t("cardTitle")}</CardTitle>
              <CardDescription>{t("cardText")}</CardDescription>
            </CardHeader>
            <CardContent className="text-sm text-fg">radius 12px · border 1px</CardContent>
          </Card>
          <div className="rounded-card-lg border border-border p-6 text-sm text-fg">
            radius 16px
          </div>
        </div>
      </Section>

      <Section title={t("radii")}>
        <div className="flex flex-wrap gap-4">
          {RADII.map(([label, className]) => (
            <div key={label} className="flex flex-col items-center gap-2">
              <span className={`size-16 border border-border-strong bg-bg-subtle ${className}`} />
              <span className="font-mono text-xs text-fg">{label}</span>
            </div>
          ))}
        </div>
      </Section>

      <Section title={t("charts")}>
        <div className="grid gap-6 md:grid-cols-[auto_1fr] md:items-center">
          <div className="flex flex-wrap gap-6">
            <ScoreGauge score={92} size={200} />
            <ScoreGauge score={71} size={200} />
            <ScoreGauge score={39} size={200} />
          </div>
          <CategoryRing
            byCategory={{ page: 2, font: 4, paragraph: 3, heading: 1, bibliography: 2 }}
            size={200}
          />
        </div>
      </Section>
    </div>
  );
}
