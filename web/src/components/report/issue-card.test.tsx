import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { type Issue } from "@/lib/api/schemas";
import { renderWithProviders } from "@/test/render";
import { IssueCard } from "./issue-card";

const issue: Issue = {
  rule_id: "bibliography.format",
  category: "bibliography",
  severity: "warning",
  checker: "llm",
  message: "Между областями описания нужен знак «. –»",
  expected: null,
  actual: "М.: Наука, 2020",
  fix: "Замените на «– М.: Наука, 2020.»",
  reference: "МИ 049-2026, Приложение И",
  reference_quote: "Образец оформления списка использованных источников",
  location: { paragraph_ids: ["p-96"], pages: [3, 4, 5], section_index: null, quote: "М.: Наука" },
  count: 1,
};

describe("IssueCard", () => {
  it("показывает серьёзность, тип проверки, место и исправление", () => {
    renderWithProviders(<IssueCard issue={issue} />);
    expect(screen.getByText("Желательно исправить")).toBeInTheDocument();
    expect(screen.getByText("ИИ")).toBeInTheDocument();
    expect(screen.getByText("стр. 3–5")).toBeInTheDocument();
    expect(screen.getByText(/Замените на/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: issue.message })).toBeInTheDocument();
  });

  it("раскрывает основание с цитатой пункта", async () => {
    renderWithProviders(<IssueCard issue={issue} />);
    expect(screen.queryByText(issue.reference_quote!)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Основание/ }));
    expect(screen.getByText(issue.reference_quote!)).toBeInTheDocument();
    expect(screen.getByText(issue.reference!)).toBeInTheDocument();
  });

  it("для ошибки уровня документа пишет «весь документ» или раздел", () => {
    renderWithProviders(
      <IssueCard
        issue={{
          ...issue,
          location: { paragraph_ids: [], pages: [], section_index: 0, quote: null },
        }}
      />,
    );
    expect(screen.getByText("раздел 1")).toBeInTheDocument();
  });
});
