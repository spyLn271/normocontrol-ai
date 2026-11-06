import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { type ReactElement, type ReactNode } from "react";
import kk from "../../messages/kk.json";
import ru from "../../messages/ru.json";

export function renderWithProviders(
  ui: ReactElement,
  { locale = "ru", ...options }: RenderOptions & { locale?: "ru" | "kk" } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider
        locale={locale}
        messages={locale === "ru" ? ru : kk}
        timeZone="Asia/Almaty"
      >
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      </NextIntlClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper, ...options });
}
