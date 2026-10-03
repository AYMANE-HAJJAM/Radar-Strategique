import type { ReviewNotification } from "@/lib/review-feedback";

export function ReviewToast({ notification, dismiss }: { notification: ReviewNotification | null; dismiss: () => void }) {
  const content = notification && <div key={notification.id} className={`review-toast ${notification.kind}`}>
    <span className="review-toast-icon" aria-hidden="true">{notification.kind === "success" ? "✓" : "!"}</span>
    <span>{notification.message}</span>
    <button type="button" aria-label="Fermer la notification" onClick={dismiss}>×</button>
  </div>;
  // Mount live regions before inserting their contents so assistive technology
  // announces successive decisions, including identical success messages.
  return <div className="review-toast-region">
    <div role="status" aria-live="polite" aria-atomic="true">{notification?.kind === "success" ? content : null}</div>
    <div role="alert" aria-live="assertive" aria-atomic="true">{notification?.kind === "error" ? content : null}</div>
  </div>;
}
