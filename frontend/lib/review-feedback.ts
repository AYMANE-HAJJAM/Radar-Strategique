import type { Result, ResultPage } from "@/types";

export type ReviewDecision = "approve" | "reject";
export type ReviewNotification = { id: number; kind: "success" | "error"; message: string };
export const REVIEW_TOAST_DURATION = 3500;

export function scheduleReviewToastDismiss(dismiss: () => void) {
  const timer = setTimeout(dismiss, REVIEW_TOAST_DURATION);
  return () => clearTimeout(timer);
}

type ReviewRequest = {
  item: Result;
  decision: ReviewDecision;
  inFlight: Set<number>;
  request: (path: string, init: RequestInit) => Promise<unknown>;
  pending: (id: number, decision: ReviewDecision | null) => void;
  notify: (kind: ReviewNotification["kind"], message: string) => void;
  confirmed: (id: number) => void;
  refresh: () => Promise<unknown>;
};

export async function submitResultReview({ item, decision, inFlight, request, pending, notify, confirmed, refresh }: ReviewRequest) {
  // Synchronous guard covers a second click before React paints disabled buttons.
  if (inFlight.has(item.id)) return;
  inFlight.add(item.id);
  pending(item.id, decision);
  try {
    try {
      await request(`/results/${item.id}/${decision}`, {
        method: "POST", body: JSON.stringify({ version: item.version }),
      });
    } catch {
      notify("error", decision === "approve" ? "Impossible de valider l’offre" : "Impossible de rejeter l’offre");
      return;
    }
    notify("success", decision === "approve" ? "Offre validée avec succès" : "Offre rejetée");
    confirmed(item.id);
    try {
      await refresh();
    } catch {
      // The review succeeded. Never report a later GET failure as a failed decision.
      notify("error", "Offre traitée, mais les résultats n’ont pas pu être actualisés");
    }
  } finally {
    inFlight.delete(item.id);
    pending(item.id, null);
  }
}

export function afterConfirmedReview(page: ResultPage, id: number): ResultPage {
  if (!page.items.some(item => item.id === id)) return page;
  const total = Math.max(0, page.total - 1);
  return {
    ...page, items: page.items.filter(item => item.id !== id), total,
    pages: Math.max(1, Math.ceil(total / page.page_size)),
    ...(page.pending_total === undefined ? {} : { pending_total: Math.max(0, page.pending_total - 1) }),
    ...(page.run_total == null ? {} : { run_total: Math.max(0, page.run_total - 1) }),
  };
}

export function reviewRefreshHref(search: URLSearchParams, page: ResultPage): string | null {
  const currentPage = Math.max(1, Number(search.get("page") || 1));
  if (page.items.length || currentPage <= Math.max(1, page.pages)) return null;
  const params = new URLSearchParams(search);
  params.set("page", String(Math.max(1, page.pages)));
  return `?${params}`;
}
