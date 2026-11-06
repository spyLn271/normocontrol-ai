import { type Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { CheckView } from "@/components/check/check-view";

interface PageProps {
  params: Promise<{ locale: string; id: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "check" });
  // результаты проверки — личные данные пользователя: не индексируем
  return { title: t("title"), robots: { index: false, follow: false } };
}

export default async function CheckPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return <CheckView id={id} />;
}
