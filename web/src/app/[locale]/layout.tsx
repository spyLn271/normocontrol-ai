import { type Metadata, type Viewport } from "next";
import { Geist_Mono, Inter } from "next/font/google";
import { notFound } from "next/navigation";
import { hasLocale, NextIntlClientProvider } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { type ReactNode } from "react";
import { SiteFooter } from "@/components/layout/site-footer";
import { SiteHeader } from "@/components/layout/site-header";
import { Providers } from "@/components/providers";
import { routing } from "@/i18n/routing";

// Шрифты скачиваются при сборке и раздаются с нашего сервера — без запросов к Google у пользователя.
const inter = Inter({
  subsets: ["latin", "cyrillic", "cyrillic-ext"],
  variable: "--font-inter",
  display: "swap",
});
const geistMono = Geist_Mono({
  subsets: ["latin", "cyrillic"],
  variable: "--font-geist-mono",
  display: "swap",
});

interface LayoutProps {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: Omit<LayoutProps, "children">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "meta" });
  return {
    title: { default: t("title"), template: "%s · Normocontrol AI" },
    description: t("description"),
    robots: { index: true, follow: true },
  };
}

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
  ],
};

export default async function LocaleLayout({ children, params }: LayoutProps) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "nav" });

  return (
    <html lang={locale} className={`${inter.variable} ${geistMono.variable}`}>
      <body className="flex min-h-screen flex-col">
        <a
          href="#main"
          className="sr-only z-50 rounded-button bg-primary px-4 py-2 text-primary-fg focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
        >
          {t("skip")}
        </a>
        <NextIntlClientProvider>
          <Providers>
            <SiteHeader />
            <main
              id="main"
              className="mx-auto w-full max-w-page flex-1 px-4 py-10 sm:px-6 sm:py-16"
            >
              {children}
            </main>
            <SiteFooter />
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
