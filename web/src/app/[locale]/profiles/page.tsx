import { type Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ProfileList } from "@/components/profiles/profile-list";

interface PageProps {
  params: Promise<{ locale: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "profiles" });
  return { title: t("title") };
}

export default async function ProfilesPage({ params }: PageProps) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("profiles");
  return (
    <div className="flex flex-col gap-8">
      <header className="flex max-w-3xl flex-col gap-3">
        <h1 className="font-display text-3xl font-semibold tracking-tight text-fg sm:text-4xl">
          {t("title")}
        </h1>
        <p className="text-base leading-relaxed text-fg-muted">{t("subtitle")}</p>
      </header>
      <ProfileList />
    </div>
  );
}
