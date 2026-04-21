"use client";

import { DownloadIcon, FilesIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { urlOfArtifact, urlOfArtifactFilesIndex } from "@/core/artifacts/utils";
import { useI18n } from "@/core/i18n/hooks";
import { getFileName } from "@/core/utils/files";

import { Tooltip } from "../tooltip";

import { useArtifacts } from "./context";

function mergeArtifactPaths(apiPaths: string[], fallback: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const p of apiPaths) {
    if (!p || seen.has(p)) continue;
    seen.add(p);
    out.push(p);
  }
  for (const p of fallback) {
    if (!p || seen.has(p)) continue;
    seen.add(p);
    out.push(p);
  }
  return out;
}

export const ArtifactTrigger = ({
  threadId,
  isMock = false,
}: {
  threadId: string;
  isMock?: boolean;
}) => {
  const { t } = useI18n();
  const { artifacts, setOpen: setArtifactsOpen } = useArtifacts();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [paths, setPaths] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fallbackArtifacts = useMemo(
    () => (artifacts ?? []).filter(Boolean),
    [artifacts],
  );
  const artifactsRef = useRef(fallbackArtifacts);
  artifactsRef.current = fallbackArtifacts;

  useEffect(() => {
    if (!pickerOpen) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setLoadError(null);
      const fallback = artifactsRef.current;
      try {
        const res = await fetch(urlOfArtifactFilesIndex({ threadId, isMock }), {
          credentials: "include",
        });
        if (!res.ok) {
          throw new Error(String(res.status));
        }
        const data = (await res.json()) as { paths?: string[] };
        const apiPaths = Array.isArray(data.paths) ? data.paths : [];
        if (!cancelled) {
          setPaths(mergeArtifactPaths(apiPaths, fallback));
        }
      } catch {
        const message = t.artifactFiles.loadFailed;
        if (!cancelled) {
          setLoadError(message);
          setPaths(mergeArtifactPaths([], fallback));
        }
        toast.error(message);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [pickerOpen, threadId, isMock, t.artifactFiles.loadFailed]);

  if (!artifacts || artifacts.length === 0) {
    return null;
  }

  return (
    <>
      <Dialog open={pickerOpen} onOpenChange={setPickerOpen}>
        <DialogContent className="gap-0 p-0 sm:max-w-lg">
          <DialogHeader className="p-6 pb-2">
            <DialogTitle>{t.artifactFiles.downloadDialogTitle}</DialogTitle>
            <DialogDescription>
              {t.artifactFiles.downloadDialogDescription}
            </DialogDescription>
          </DialogHeader>
          <div className="border-t px-6 py-4">
            {loading ? (
              <p className="text-muted-foreground text-sm">{t.common.loading}</p>
            ) : loadError && paths.length === 0 ? (
              <p className="text-destructive text-sm">{loadError}</p>
            ) : paths.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                {t.artifactFiles.emptyList}
              </p>
            ) : (
              <ScrollArea className="max-h-72 pr-3">
                <ul className="flex w-full flex-col gap-2">
                  {paths.map((filepath) => {
                    const baseName = getFileName(filepath);
                    return (
                      <li
                        key={filepath}
                        className="flex w-full min-w-0 flex-col gap-3 rounded-md border px-3 py-2 sm:flex-row sm:items-center sm:justify-between sm:gap-3"
                      >
                        <Tooltip content={baseName}>
                          <div className="min-w-0 flex-1 cursor-default space-y-0.5">
                            <div className="text-sm leading-snug font-medium [overflow-wrap:anywhere] break-words line-clamp-2">
                              {baseName}
                            </div>
                          </div>
                        </Tooltip>
                        <Button
                          variant="secondary"
                          size="sm"
                          className="w-full shrink-0 sm:w-auto sm:self-start"
                          asChild
                        >
                          <a
                            href={urlOfArtifact({
                              filepath,
                              threadId,
                              download: true,
                              isMock,
                            })}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <DownloadIcon className="size-4" />
                            {t.artifactFiles.downloadThisFile}
                          </a>
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              </ScrollArea>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <Tooltip content={t.artifactFiles.downloadDialogDescription}>
        <Button
          className="text-muted-foreground hover:text-foreground"
          variant="ghost"
          onClick={() => setPickerOpen(true)}
        >
          <DownloadIcon />
          {t.common.download}
        </Button>
      </Tooltip>

      <Tooltip content={t.common.artifacts}>
        <Button
          className="text-muted-foreground hover:text-foreground"
          variant="ghost"
          onClick={() => {
            setArtifactsOpen(true);
          }}
        >
          <FilesIcon />
          {t.common.artifacts}
        </Button>
      </Tooltip>
    </>
  );
};
