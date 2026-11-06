import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import sample from "@/mocks/kru-sample.report.json";
import { reportSchema } from "@/lib/api/schemas";
import { renderWithProviders } from "@/test/render";
import { ReportView } from "./report-view";

vi.mock("@/i18n/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

const report = reportSchema.parse(sample);
const check = {
  id: "c1",
  status: "done" as const,
  step: null,
  steps: [],
  filename: report.document.filename,
  profile_id: report.profile.id,
  created_at: report.created_at,
  updated_at: report.created_at,
  expires_at: null,
  error: null,
  report,
  annotated_url: "/api/checks/c1/annotated.docx",
};

describe("ReportView", () => {
  it("показывает балл, файл, ссылку на .docx с комментариями и все замечания", () => {
    renderWithProviders(<ReportView check={check} report={report} />);
    expect(screen.getByRole("img", { name: /39 из 100/ })).toBeInTheDocument();
    expect(screen.getByText("kursovaya_rabota.docx")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Скачать .docx/ })).toHaveAttribute(
      "href",
      "/api/checks/c1/annotated.docx",
    );
    const list = screen.getByRole("region", { name: "Замечания" });
    expect(within(list).getAllByRole("article")).toHaveLength(report.issues.length);
  });

  it("фильтрует замечания по серьёзности", async () => {
    renderWithProviders(<ReportView check={check} report={report} />);
    const list = screen.getByRole("region", { name: "Замечания" });
    const severityGroup = screen.getByRole("group", { name: "Серьёзность" });
    await userEvent.click(within(severityGroup).getByRole("button", { name: /Ошибка/ }));
    expect(within(list).getAllByRole("article")).toHaveLength(4);
    expect(screen.getByText("Показано 4 из 7")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Сбросить фильтры" }));
    expect(within(list).getAllByRole("article")).toHaveLength(7);
  });
});
