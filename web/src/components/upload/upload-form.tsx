"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { FileText, UploadCloud, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { type DragEvent, type FormEvent, useId, useRef, useState } from "react";
import { errorText } from "@/components/check/check-view";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectItemText,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useRouter } from "@/i18n/navigation";
import { createCheck, listProfiles, MAX_UPLOAD_MB } from "@/lib/api/client";
import { formatFileSize } from "@/lib/format";
import { ACCEPT_DOCX, type FileProblem, validateDocx } from "@/lib/upload";
import { cn } from "@/lib/utils";

export function UploadForm() {
  const t = useTranslations("upload");
  const tAll = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const ids = { file: useId(), profile: useId(), annotate: useId(), error: useId() };

  const [file, setFile] = useState<File | null>(null);
  const [fileProblem, setFileProblem] = useState<FileProblem | "noFile" | "multiple" | null>(null);
  const [profileId, setProfileId] = useState<string>("");
  const [profileMissing, setProfileMissing] = useState(false);
  const [annotate, setAnnotate] = useState(true);
  const [dragging, setDragging] = useState(false);

  const profiles = useQuery({
    queryKey: ["profiles"],
    queryFn: listProfiles,
    staleTime: 5 * 60_000,
  });
  const submit = useMutation({
    mutationFn: createCheck,
    onSuccess: (check) => router.push(`/checks/${check.id}`),
  });

  function accept(files: FileList | null) {
    if (!files || files.length === 0) return;
    if (files.length > 1) {
      setFileProblem("multiple");
      return;
    }
    const candidate = files[0]!;
    const problem = validateDocx(candidate, MAX_UPLOAD_MB);
    setFileProblem(problem);
    setFile(problem ? null : candidate);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files);
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const noFile = !file;
    const noProfile = !profileId;
    if (noFile) setFileProblem("noFile");
    setProfileMissing(noProfile);
    if (noFile || noProfile) return;
    submit.mutate({ file, profileId, annotate });
  }

  const problemText =
    fileProblem === null ? null : t(`errors.${fileProblem}`, { size: MAX_UPLOAD_MB });
  const selectable = profiles.data ?? [];

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-6"
      aria-labelledby="upload-title"
    >
      <h2 id="upload-title" className="text-lg font-semibold text-fg">
        {t("title")}
      </h2>

      <div className="flex flex-col gap-2">
        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "flex flex-col items-center justify-center gap-3 rounded-card border border-dashed px-6 py-10 text-center transition-colors",
            dragging ? "border-accent bg-accent-subtle" : "border-border-strong bg-bg-subtle",
            fileProblem && "border-error",
          )}
        >
          {file ? (
            <div className="flex w-full max-w-md items-center gap-3 rounded-input border border-border bg-bg px-3 py-2 text-left">
              <FileText className="size-5 shrink-0 text-accent" aria-hidden />
              <div className="min-w-0 flex-1">
                <p className="sr-only">{t("selected")}</p>
                <p className="truncate text-sm font-medium text-fg">{file.name}</p>
                <p className="text-xs text-fg">{formatFileSize(file.size, locale)}</p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label={t("remove")}
                onClick={() => {
                  setFile(null);
                  if (inputRef.current) inputRef.current.value = "";
                }}
              >
                <X aria-hidden />
              </Button>
            </div>
          ) : (
            <>
              <UploadCloud className="size-8 text-fg-muted" aria-hidden />
              <p className="text-sm text-fg">{t("dropzone")}</p>
              <p className="text-xs text-fg">{t("or")}</p>
            </>
          )}
          <input
            ref={inputRef}
            id={ids.file}
            type="file"
            accept={ACCEPT_DOCX}
            className="sr-only"
            aria-describedby={`${ids.file}-hint ${problemText ? ids.error : ""}`.trim()}
            aria-invalid={Boolean(problemText)}
            onChange={(event) => accept(event.target.files)}
          />
          <Button type="button" variant="secondary" onClick={() => inputRef.current?.click()}>
            {t("choose")}
          </Button>
          <label htmlFor={ids.file} className="sr-only">
            {t("choose")}
          </label>
          <p id={`${ids.file}-hint`} className="text-xs text-fg">
            {t("hint", { size: MAX_UPLOAD_MB })}
          </p>
        </div>
        {problemText && (
          <p id={ids.error} role="alert" className="text-sm text-error-fg">
            {problemText}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor={ids.profile}>{t("profile")}</Label>
        <Select
          value={profileId}
          onValueChange={(value) => {
            setProfileId(value);
            setProfileMissing(false);
          }}
          disabled={profiles.isPending || profiles.isError}
        >
          <SelectTrigger id={ids.profile} aria-invalid={profileMissing}>
            <SelectValue
              placeholder={
                profiles.isPending
                  ? t("profilesLoading")
                  : profiles.isError
                    ? t("profilesError")
                    : t("profilePlaceholder")
              }
            />
          </SelectTrigger>
          <SelectContent>
            {selectable.map((profile) => (
              <SelectItem key={profile.id} value={profile.id}>
                <span className="flex flex-col gap-0.5">
                  <SelectItemText>{profile.title}</SelectItemText>
                  {profile.status === "draft" && (
                    <Badge tone="warning" className="w-fit">
                      {t("draft")}
                    </Badge>
                  )}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {profileMissing && (
          <p role="alert" className="text-sm text-error-fg">
            {t("errors.noProfile")}
          </p>
        )}
        {profiles.isError && (
          <p role="alert" className="text-sm text-error-fg">
            {errorText(profiles.error, tAll)}
          </p>
        )}
      </div>

      <div className="flex items-start gap-3">
        <Checkbox
          id={ids.annotate}
          checked={annotate}
          onCheckedChange={(value) => setAnnotate(value === true)}
          aria-describedby={`${ids.annotate}-hint`}
        />
        <div className="flex flex-col gap-0.5">
          <Label htmlFor={ids.annotate}>{t("annotate")}</Label>
          <p id={`${ids.annotate}-hint`} className="text-xs text-fg-muted">
            {t("annotateHint")}
          </p>
        </div>
      </div>

      {submit.isError && <Alert tone="error">{errorText(submit.error, tAll)}</Alert>}

      <Button
        type="submit"
        size="lg"
        disabled={submit.isPending}
        className="w-full sm:w-auto sm:self-start"
      >
        {submit.isPending ? t("submitting") : t("submit")}
      </Button>
    </form>
  );
}
