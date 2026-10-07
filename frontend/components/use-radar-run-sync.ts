"use client";
import { useEffect, useRef } from "react";
import { api } from "@/lib/api";
import { startRadarRunSync } from "@/lib/radar-run-sync";
import type { Run } from "@/types";

export function useRadarRunSync(radarId: string, run: Run | null, updateRun: (run: Run) => void,
  refreshResults: () => Promise<unknown>, onError: (reason: unknown) => void) {
  const current = useRef({ run, updateRun, refreshResults, onError });
  useEffect(() => { current.current = { run, updateRun, refreshResults, onError }; },
    [run, updateRun, refreshResults, onError]);
  useEffect(() => startRadarRunSync({
    currentRun: () => current.current.run,
    requestRun: id => api<Run>(`/runs/${id}`, { cache: "no-store" }),
    updateRun: next => { current.current.run = next; current.current.updateRun(next); },
    refreshResults: () => current.current.refreshResults(),
    onError: reason => current.current.onError(reason),
    document, window,
  }), [radarId]);
}
