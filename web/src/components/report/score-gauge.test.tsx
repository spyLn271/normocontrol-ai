import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "@/test/render";
import { ScoreGauge } from "./score-gauge";

describe("ScoreGauge", () => {
  it("рендерит доступную подпись и SVG-шкалу Bklit", () => {
    const { container } = renderWithProviders(<ScoreGauge score={39} />);
    const figure = screen.getByRole("img", { name: "Балл соответствия: 39 из 100" });
    expect(figure).toHaveAttribute("data-tone", "error");
    expect(screen.getByText("Балл соответствия")).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("ограничивает значение диапазоном 0–100 и выбирает тон", () => {
    renderWithProviders(<ScoreGauge score={140} />);
    expect(screen.getByRole("img", { name: "Балл соответствия: 100 из 100" })).toHaveAttribute(
      "data-tone",
      "ok",
    );
  });

  it("локализуется на казахский", () => {
    renderWithProviders(<ScoreGauge score={72} />, { locale: "kk" });
    expect(screen.getByRole("img", { name: "Сәйкестік балы: 100-ден 72" })).toHaveAttribute(
      "data-tone",
      "warning",
    );
  });
});
