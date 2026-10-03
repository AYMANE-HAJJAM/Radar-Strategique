import type { Result } from "@/types";
import type { ReviewDecision } from "@/lib/review-feedback";

export function ResultActions({ item, radarId, status, reviewing, onReview }: {
  item: Result; radarId: string; status: string; reviewing?: ReviewDecision;
  onReview: (item: Result, decision: ReviewDecision) => void;
}) {
  const busy = !!reviewing;
  return <div className="compact-actions">
    {item.url ? <a className="view-link" href={item.url} target="_blank" rel="noopener noreferrer">
      {radarId === "1" ? "Voir l’offre ↗" : "Voir la source ↗"}
    </a> : <span className="source-unavailable">Source indisponible</span>}
    {status === "pending" && <>
      <button type="button" disabled={busy} aria-busy={reviewing === "approve"} onClick={() => onReview(item, "approve")}>
        {reviewing === "approve" && <span className="review-spinner" aria-hidden="true" />}
        {reviewing === "approve" ? "Validation..." : "Valider"}
      </button>
      <button type="button" className="reject-action" disabled={busy} aria-busy={reviewing === "reject"} onClick={() => onReview(item, "reject")}>
        {reviewing === "reject" && <span className="review-spinner" aria-hidden="true" />}
        {reviewing === "reject" ? "Rejet..." : "Rejeter"}
      </button>
    </>}
  </div>;
}
