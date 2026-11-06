export type FileProblem = "extension" | "size" | "empty";

const DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

/** Клиентская проверка до загрузки; окончательную проверку делает сервер. */
export function validateDocx(file: File, maxMb: number): FileProblem | null {
  const name = file.name.toLowerCase();
  if (
    !name.endsWith(".docx") ||
    (file.type && file.type !== DOCX_MIME && file.type !== "application/octet-stream")
  ) {
    return "extension";
  }
  if (file.size === 0) return "empty";
  if (file.size > maxMb * 1024 * 1024) return "size";
  return null;
}

export const ACCEPT_DOCX = `.docx,${DOCX_MIME}`;
