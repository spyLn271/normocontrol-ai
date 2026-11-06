"use client";

import { useQuery } from "@tanstack/react-query";
import { BookOpen } from "lucide-react";
import { useTranslations } from "next-intl";
import { errorText } from "@/components/check/check-view";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { listProfiles } from "@/lib/api/client";
import { type Profile } from "@/lib/api/schemas";

const STATUS_TONE = { draft: "warning", active: "ok", deprecated: "neutral" } as const;

export function ProfileList() {
  const t = useTranslations();
  const query = useQuery({ queryKey: ["profiles"], queryFn: listProfiles, staleTime: 5 * 60_000 });

  if (query.isPending) {
    return (
      <p role="status" className="text-sm text-fg-muted">
        {t("profiles.loading")}
      </p>
    );
  }
  if (query.isError) {
    return <Alert tone="error">{errorText(query.error, t)}</Alert>;
  }
  if (query.data.length === 0) {
    return <p className="text-sm text-fg-muted">{t("profiles.empty")}</p>;
  }
  return (
    <ul className="grid gap-4 md:grid-cols-2">
      {query.data.map((profile) => (
        <li key={profile.id}>
          <ProfileCard profile={profile} />
        </li>
      ))}
    </ul>
  );
}

function ProfileCard({ profile }: { profile: Profile }) {
  const t = useTranslations();
  const label = (group: "docTypes" | "languages", key: string) =>
    t.has(`${group}.${key}`) ? t(`${group}.${key}`) : key;
  return (
    <article className="flex h-full flex-col gap-4 rounded-card border border-border p-5">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={STATUS_TONE[profile.status]}>{t(`profiles.status.${profile.status}`)}</Badge>
          {profile.version && (
            <span className="text-xs text-fg-muted">
              {t("profiles.version", { version: profile.version })}
            </span>
          )}
          <span className="ml-auto font-mono text-xs text-fg-muted">{profile.id}</span>
        </div>
        <h2 className="text-base leading-snug font-semibold text-fg">{profile.title}</h2>
        {profile.description && <p className="text-sm text-fg-muted">{profile.description}</p>}
      </header>
      <dl className="mt-auto grid gap-3 text-sm">
        {profile.doc_types.length > 0 && (
          <div>
            <dt className="text-xs font-medium text-fg-muted">{t("profiles.docTypes")}</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {profile.doc_types.map((type) => (
                <Badge key={type} tone="outline">
                  {label("docTypes", type)}
                </Badge>
              ))}
            </dd>
          </div>
        )}
        {profile.languages.length > 0 && (
          <div>
            <dt className="text-xs font-medium text-fg-muted">{t("profiles.languages")}</dt>
            <dd className="mt-1 text-fg">
              {profile.languages.map((l) => label("languages", l)).join(", ")}
            </dd>
          </div>
        )}
        <div>
          <dt className="text-xs font-medium text-fg-muted">{t("profiles.sources")}</dt>
          <dd className="mt-1">
            {profile.rag_sources.length > 0 ? (
              <ul className="flex flex-col gap-1">
                {[...profile.rag_sources]
                  .sort((a, b) => a.priority - b.priority)
                  .map((source) => (
                    <li key={source.source} className="flex items-center gap-2 text-fg">
                      <BookOpen className="size-3.5 shrink-0 text-fg-muted" aria-hidden />
                      {source.source}
                    </li>
                  ))}
              </ul>
            ) : (
              <span className="text-fg-muted">{t("profiles.noSources")}</span>
            )}
          </dd>
        </div>
      </dl>
    </article>
  );
}
