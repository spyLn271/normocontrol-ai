import { type z } from "zod";
import { ApiError, errorFromResponse } from "./errors";
import * as mock from "./mock";
import { type CheckStatus, checkStatusSchema, type Profile, profileListSchema } from "./schemas";

export const MOCK_MODE = process.env.NEXT_PUBLIC_API_MOCK === "1";
export const MAX_UPLOAD_MB = 20;

export interface CreateCheckInput {
  file: File;
  profileId: string;
  annotate: boolean;
  useLlm?: boolean;
}

async function request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers: { Accept: "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("network", "network", 0);
  }
  if (!response.ok) {
    throw await errorFromResponse(response);
  }
  const data: unknown = await response.json();
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    throw new ApiError("invalid_response", "invalid_response", response.status);
  }
  return parsed.data;
}

export async function listProfiles(): Promise<Profile[]> {
  if (MOCK_MODE) return mock.listProfiles();
  return request("/api/profiles", profileListSchema);
}

export async function createCheck(input: CreateCheckInput): Promise<CheckStatus> {
  if (MOCK_MODE) return mock.createCheck(input);
  const form = new FormData();
  form.set("file", input.file);
  form.set("profile_id", input.profileId);
  form.set("annotate", String(input.annotate));
  if (input.useLlm !== undefined) form.set("use_llm", String(input.useLlm));
  return request("/api/checks", checkStatusSchema, { method: "POST", body: form });
}

export async function getCheck(id: string): Promise<CheckStatus> {
  if (MOCK_MODE) return mock.getCheck(id);
  return request(`/api/checks/${encodeURIComponent(id)}`, checkStatusSchema);
}

export async function deleteCheck(id: string): Promise<void> {
  if (MOCK_MODE) return mock.deleteCheck(id);
  let response: Response;
  try {
    response = await fetch(`/api/checks/${encodeURIComponent(id)}`, { method: "DELETE" });
  } catch {
    throw new ApiError("network", "network", 0);
  }
  if (!response.ok && response.status !== 404) {
    throw await errorFromResponse(response);
  }
}
