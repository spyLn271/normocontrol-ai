/**
 * Контракт API (FastAPI) — зеркало normocontrol/report/model.py и api/schemas.py.
 * Ответы сервера валидируются zod: при несовпадении формата UI показывает понятную ошибку,
 * а не падает в глубине компонента.
 */
import { z } from "zod";

export const SEVERITIES = ["error", "warning", "info"] as const;
export const CHECKERS = ["rule", "structure", "llm"] as const;
export const CATEGORIES = [
  "page",
  "font",
  "paragraph",
  "text",
  "heading",
  "structure",
  "figures",
  "tables",
  "bibliography",
  "requisites",
  "other",
] as const;
export const STEP_IDS = ["parse", "rules", "structure", "llm", "report"] as const;

export const severitySchema = z.enum(SEVERITIES);
export const checkerSchema = z.enum(CHECKERS);

export const locationSchema = z.object({
  paragraph_ids: z.array(z.string()).default([]),
  pages: z.array(z.number().int()).default([]),
  section_index: z.number().int().nullable().default(null),
  quote: z.string().nullable().default(null),
});

export const issueSchema = z.object({
  rule_id: z.string(),
  // категорию не ограничиваем перечнем: новая категория на бэкенде не должна ломать UI
  category: z.string(),
  severity: severitySchema,
  checker: checkerSchema.default("rule"),
  message: z.string(),
  expected: z.string().nullable().default(null),
  actual: z.string().nullable().default(null),
  fix: z.string().nullable().default(null),
  reference: z.string().nullable().default(null),
  reference_quote: z.string().nullable().default(null),
  location: locationSchema,
  count: z.number().int().min(1).default(1),
});

export const noticeSchema = z.object({
  code: z.string(),
  level: z.enum(["info", "warning"]).default("info"),
  message: z.string(),
});

export const checkRunSchema = z.object({
  rule_id: z.string(),
  checker: checkerSchema,
  status: z.enum(["ok", "skipped", "failed"]),
  issues: z.number().int().default(0),
  detail: z.string().nullable().default(null),
});

export const reportSchema = z.object({
  schema_version: z.string(),
  created_at: z.string(),
  duration_ms: z.number().int(),
  document: z.object({
    filename: z.string().nullable(),
    paragraphs: z.number().int(),
    words: z.number().int(),
    tables: z.number().int(),
    images: z.number().int(),
    sections: z.number().int(),
    pages_estimated: z.number().int().nullable().default(null),
    page_source: z.string().nullable().default(null),
  }),
  profile: z.object({
    id: z.string(),
    title: z.string(),
    status: z.string(),
    version: z.string().nullable().default(null),
  }),
  engine: z.object({
    version: z.string(),
    llm_model: z.string().nullable().default(null),
    embedding_model: z.string().nullable().default(null),
  }),
  score: z.number().int().min(0).max(100),
  summary: z.object({
    total: z.number().int(),
    by_severity: z.record(z.string(), z.number().int()),
    by_category: z.record(z.string(), z.number().int()),
  }),
  issues: z.array(issueSchema),
  notices: z.array(noticeSchema).default([]),
  checks: z.array(checkRunSchema).default([]),
});

export const profileSchema = z.object({
  id: z.string(),
  title: z.string(),
  status: z.enum(["draft", "active", "deprecated"]),
  version: z.string().nullable().default(null),
  description: z.string().nullable().default(null),
  doc_types: z.array(z.string()).default([]),
  languages: z.array(z.string()).default([]),
  rag_sources: z.array(z.object({ source: z.string(), priority: z.number().int() })).default([]),
});

export const profileListSchema = z.array(profileSchema);

export const checkStatusValues = ["queued", "running", "done", "failed", "expired"] as const;

export const checkStepSchema = z.object({
  id: z.string(),
  title: z.string(),
  state: z.enum(["pending", "active", "done", "skipped"]),
});

export const apiErrorBodySchema = z.object({
  error: z.object({ code: z.string(), message: z.string() }),
});

export const checkStatusSchema = z.object({
  id: z.string(),
  status: z.enum(checkStatusValues),
  step: z.string().nullable().default(null),
  steps: z.array(checkStepSchema).default([]),
  filename: z.string().nullable().default(null),
  profile_id: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  expires_at: z.string().nullable().default(null),
  error: apiErrorBodySchema.shape.error.nullable().default(null),
  report: reportSchema.nullable().default(null),
  annotated_url: z.string().nullable().default(null),
});

export type Severity = z.infer<typeof severitySchema>;
export type Checker = z.infer<typeof checkerSchema>;
export type Issue = z.infer<typeof issueSchema>;
export type Notice = z.infer<typeof noticeSchema>;
export type Report = z.infer<typeof reportSchema>;
export type Profile = z.infer<typeof profileSchema>;
export type CheckStatus = z.infer<typeof checkStatusSchema>;
export type CheckStep = z.infer<typeof checkStepSchema>;
export type CheckState = CheckStatus["status"];

export function isFinal(status: CheckState): boolean {
  return status === "done" || status === "failed" || status === "expired";
}
