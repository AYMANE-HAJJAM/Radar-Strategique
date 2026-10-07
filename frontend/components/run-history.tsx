"use client";
import { useCallback, useEffect, useState } from "react";
import { RunHistoryTable } from "@/components/run-history-table";
import { EmptyResults, ResultsError, TableSkeleton } from "@/components/table-state";
import { api } from "@/lib/api";
import type { Page, Run } from "@/types";

export function RunHistory({ radarId, historyHref, refreshKey = 0 }: { radarId: string; historyHref: string; refreshKey?: number }) {
  const [data, setData] = useState<{ radarId: string; page: Page<Run> } | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => setAttempt(value => value + 1), []);
  useEffect(() => {
    let cancelled = false;
    api<Page<Run>>(`/radars/${radarId}/runs?page_size=50`, { cache: "no-store" }).then(page => {
      if (!cancelled) { setData({ radarId, page }); setError(false); }
    }).catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, [radarId, attempt, refreshKey]);
  if (error && (!data || data.radarId !== radarId)) return <ResultsError retry={retry} />;
  if (!data || data.radarId !== radarId) return <TableSkeleton />;
  if (!data.page.items.length) return <EmptyResults label="Aucune recherche précédente." />;
  return <>{error && <p role="alert">Actualisation impossible. <button className="text-button" onClick={retry}>Réessayer</button></p>}<RunHistoryTable radarId={radarId} runs={data.page.items} historyHref={historyHref} /></>;
}
