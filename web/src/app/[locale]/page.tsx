import { Cpu, ShieldCheck, Ruler } from "lucide-react";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { UploadForm } from "@/components/upload/upload-form";

interface PageProps {
  params: Promise<{ locale: string }>;
}

export default async function HomePage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("home");
  const features = [
    { icon: Ruler, title: t("features.rulesTitle"), text: t("features.rulesText") },
    { icon: Cpu, title: t("features.aiTitle"), text: t("features.aiText") },
    { icon: ShieldCheck, title: t("features.privacyTitle"), text: t("features.privacyText") },
  ];

  return (
    <div className="grid gap-section">
      <section className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,480px)] lg:items-start">
        <div className="flex flex-col gap-5">
          <p className="w-fit rounded-badge border border-border px-3 py-1 text-xs font-medium text-fg">
            {t("eyebrow")}
          </p>
          <h1 className="font-display text-4xl leading-tight font-semibold tracking-tight text-fg sm:text-5xl">
            {t("title")}
          </h1>
          <p className="max-w-xl text-base leading-relaxed text-fg-muted sm:text-lg">
            {t("subtitle")}
          </p>
        </div>
        <div className="rounded-card-lg border border-border p-6 sm:p-8">
          <UploadForm />
        </div>
      </section>
      <section aria-label={t("eyebrow")} className="grid gap-4 md:grid-cols-3">
        {features.map(({ icon: Icon, title, text }) => (
          <article key={title} className="rounded-card border border-border p-5">
            <Icon className="size-5 text-accent" aria-hidden />
            <h2 className="mt-3 text-base font-semibold text-fg">{title}</h2>
            <p className="mt-1 text-sm leading-relaxed text-fg-muted">{text}</p>
          </article>
        ))}
      </section>
    </div>
  );
}
