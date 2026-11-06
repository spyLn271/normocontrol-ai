/**
 * Мок-режим (NEXT_PUBLIC_API_MOCK=1): UI работает без бэкенда.
 * Проверка «идёт» ~4 секунды по шагам, затем отдаёт реальный отчёт из tests/fixtures.
 */
import sampleReport from "@/mocks/kru-sample.report.json";
import { ApiError } from "./errors";
import {
  type CheckStatus,
  type CheckStep,
  type Issue,
  type Profile,
  reportSchema,
  STEP_IDS,
} from "./schemas";

const STEP_MS = 800;
const TTL_MS = 60 * 60 * 1000;
const STORAGE_KEY = "nc-mock-checks";

const STEP_TITLES: Record<(typeof STEP_IDS)[number], string> = {
  parse: "Чтение файла",
  rules: "Правила оформления",
  structure: "Структура документа",
  llm: "ИИ-проверки",
  report: "Формирование отчёта",
};

export const MOCK_PROFILES: Profile[] = [
  {
    id: "kru-mi-049-2026",
    title: "КРУ им. А. Байтұрсынұлы — курсовые и дипломные работы (МИ 049-2026)",
    status: "active",
    version: "2026",
    description:
      "Курсовые и дипломные работы (проекты), в том числе групповые дипломные проекты в формате стартапа.",
    doc_types: ["coursework", "thesis"],
    languages: ["ru", "kk"],
    rag_sources: [{ source: "МИ 049-2026", priority: 1 }],
  },
  {
    id: "gost-7.32-2017",
    title: "ГОСТ 7.32-2017 — Отчёт о научно-исследовательской работе",
    status: "draft",
    version: "2017",
    description: null,
    doc_types: ["report", "coursework", "thesis"],
    languages: ["ru", "kk"],
    rag_sources: [
      { source: "ГОСТ 7.32-2017", priority: 1 },
      { source: "ГОСТ 7.1-2003", priority: 2 },
    ],
  },
  {
    id: "kz-rules-236-2023",
    title: "Документы организаций РК — Правила документирования (приказ № 236)",
    status: "active",
    version: "2023-08-25",
    description: "Письма, служебные записки, заявления, справки.",
    doc_types: ["letter", "memo", "application", "certificate"],
    languages: ["kk", "ru"],
    rag_sources: [{ source: "Правила документирования № 236", priority: 1 }],
  },
  {
    id: "kz-order-236-2023",
    title: "Приказ организации РК — Правила документирования (приказ № 236)",
    status: "active",
    version: "2023-08-25",
    description: null,
    doc_types: ["order"],
    languages: ["kk", "ru"],
    rag_sources: [{ source: "Правила документирования № 236", priority: 1 }],
  },
];

const LLM_EXAMPLE: Issue = {
  rule_id: "bibliography.format",
  category: "bibliography",
  severity: "warning",
  checker: "llm",
  message: "Между областями библиографического описания должен стоять знак «. –».",
  expected: null,
  actual: "М.: Наука, 2020",
  fix: "Замените на «– М.: Наука, 2020. – 300 с.»",
  reference: "МИ 049-2026, Приложение И",
  reference_quote:
    "Образец оформления списка использованных источников: 1 Осин А.В. Мультимедиа в образовании: контекст информатизации / А. В. Осин. - М.: Издательский сервис, 2024. – 320 с.",
  location: { paragraph_ids: ["p-96"], pages: [8], section_index: null, quote: "М.: Наука, 2020" },
  count: 1,
};

interface StoredCheck {
  id: string;
  createdAt: number;
  filename: string;
  profileId: string;
  annotate: boolean;
}

const memory = new Map<string, StoredCheck>();

function load(): Map<string, StoredCheck> {
  if (typeof window === "undefined") return memory;
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    if (raw) {
      for (const item of JSON.parse(raw) as StoredCheck[]) memory.set(item.id, item);
    }
  } catch {
    // sessionStorage недоступен (приватный режим) — работаем в памяти
  }
  return memory;
}

function save(store: Map<string, StoredCheck>): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...store.values()]));
  } catch {
    // без сохранения между перезагрузками
  }
}

const delay = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function listProfiles(): Promise<Profile[]> {
  await delay(150);
  return MOCK_PROFILES;
}

export async function createCheck(input: {
  file: File;
  profileId: string;
  annotate: boolean;
}): Promise<CheckStatus> {
  await delay(300);
  if (!input.file.name.toLowerCase().endsWith(".docx")) {
    throw new ApiError("unsupported_media_type", "Поддерживаются только файлы .docx", 415);
  }
  if (!MOCK_PROFILES.some((p) => p.id === input.profileId)) {
    throw new ApiError("profile_not_found", `Профиль «${input.profileId}» не найден`, 404);
  }
  const store = load();
  const id = `mock-${Date.now().toString(36)}`;
  store.set(id, {
    id,
    createdAt: Date.now(),
    filename: input.file.name,
    profileId: input.profileId,
    annotate: input.annotate,
  });
  save(store);
  return status(store.get(id)!, Date.now());
}

/** Готовый отчёт по адресу /checks/demo — для разработки и скриншотов. */
export const DEMO_CHECK_ID = "demo";

export async function getCheck(id: string): Promise<CheckStatus> {
  await delay(80);
  if (id === DEMO_CHECK_ID) {
    const now = Date.now();
    return status(
      {
        id,
        createdAt: now - 10_000,
        filename: "kursovaya_rabota.docx",
        profileId: "kru-mi-049-2026",
        annotate: true,
      },
      now,
    );
  }
  const stored = load().get(id);
  if (!stored) throw new ApiError("check_not_found", "Проверка не найдена", 404);
  return status(stored, Date.now());
}

export async function deleteCheck(id: string): Promise<void> {
  await delay(100);
  const store = load();
  store.delete(id);
  save(store);
}

function status(stored: StoredCheck, now: number): CheckStatus {
  const elapsed = now - stored.createdAt;
  const iso = (ms: number) => new Date(ms).toISOString();
  const base = {
    id: stored.id,
    filename: stored.filename,
    profile_id: stored.profileId,
    created_at: iso(stored.createdAt),
    updated_at: iso(now),
    expires_at: iso(stored.createdAt + TTL_MS),
    error: null,
    annotated_url: null,
  };
  if (elapsed > TTL_MS) {
    return { ...base, status: "expired", step: null, steps: [], report: null };
  }
  const active = Math.floor(elapsed / STEP_MS) - 1; // первые 800 мс — в очереди
  const steps: CheckStep[] = STEP_IDS.map((stepId, index) => ({
    id: stepId,
    title: STEP_TITLES[stepId],
    state: index < active ? "done" : index === active ? "active" : "pending",
  }));
  if (active < 0) {
    return { ...base, status: "queued", step: null, steps, report: null };
  }
  if (active < STEP_IDS.length) {
    return { ...base, status: "running", step: STEP_IDS[active] ?? null, steps, report: null };
  }
  const report = reportSchema.parse(sampleReport);
  const profile = MOCK_PROFILES.find((p) => p.id === stored.profileId) ?? MOCK_PROFILES[0]!;
  const issues = [...report.issues, LLM_EXAMPLE];
  return {
    ...base,
    status: "done",
    step: null,
    steps: steps.map((step) => ({ ...step, state: "done" })),
    report: {
      ...report,
      document: { ...report.document, filename: stored.filename },
      profile: {
        id: profile.id,
        title: profile.title,
        status: profile.status,
        version: profile.version,
      },
      issues,
      // в мок-отчёт добавлено ИИ-замечание, поэтому уведомление «ИИ отключён» убираем
      notices: report.notices.filter((notice) => notice.code !== "llm_disabled"),
      summary: {
        ...report.summary,
        total: issues.length,
        by_severity: {
          ...report.summary.by_severity,
          warning: (report.summary.by_severity.warning ?? 0) + 1,
        },
        by_category: {
          ...report.summary.by_category,
          bibliography: (report.summary.by_category.bibliography ?? 0) + 1,
        },
      },
    },
  };
}
