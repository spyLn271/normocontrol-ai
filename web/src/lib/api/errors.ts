import { apiErrorBodySchema } from "./schemas";

/** Ошибка API с машиночитаемым кодом и сообщением для пользователя. */
export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

export async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // тело не JSON — например, 502 от прокси
  }
  const parsed = apiErrorBodySchema.safeParse(body);
  if (parsed.success) {
    return new ApiError(parsed.data.error.code, parsed.data.error.message, response.status);
  }
  return new ApiError(
    `http_${response.status}`,
    response.statusText || "Request failed",
    response.status,
  );
}
