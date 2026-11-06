import { describe, expect, it } from "vitest";
import { validateDocx } from "./upload";

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function file(name: string, size: number, type = DOCX): File {
  return new File([new Uint8Array(size)], name, { type });
}

describe("validateDocx", () => {
  it("принимает .docx в пределах лимита", () => {
    expect(validateDocx(file("work.docx", 1024), 20)).toBeNull();
    expect(validateDocx(file("WORK.DOCX", 10, ""), 20)).toBeNull();
  });

  it("отклоняет другие форматы", () => {
    expect(validateDocx(file("work.doc", 10, "application/msword"), 20)).toBe("extension");
    expect(validateDocx(file("work.pdf", 10, "application/pdf"), 20)).toBe("extension");
  });

  it("отклоняет пустые и слишком большие файлы", () => {
    expect(validateDocx(file("empty.docx", 0), 20)).toBe("empty");
    expect(validateDocx(file("big.docx", 2 * 1024 * 1024 + 1), 2)).toBe("size");
  });
});
