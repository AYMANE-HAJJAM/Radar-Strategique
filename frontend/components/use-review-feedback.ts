"use client";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { scheduleReviewToastDismiss, submitResultReview } from "@/lib/review-feedback";
import type { ReviewDecision, ReviewNotification } from "@/lib/review-feedback";
import type { Result } from "@/types";

export function useReviewFeedback(refresh: () => Promise<unknown>, confirmed: (id: number) => void) {
  const inFlight = useRef(new Set<number>());
  const refreshCurrentView = useRef(refresh);
  const notificationId = useRef(0);
  const [reviewing, setReviewing] = useState<Record<number, ReviewDecision>>({});
  const [notification, setNotification] = useState<ReviewNotification | null>(null);
  useEffect(() => { refreshCurrentView.current = refresh; }, [refresh]);
  useEffect(() => {
    if (!notification) return;
    return scheduleReviewToastDismiss(() => setNotification(current => current?.id === notification.id ? null : current));
  }, [notification]);

  function review(item: Result, decision: ReviewDecision) {
    return submitResultReview({
      item, decision, inFlight: inFlight.current, request: api,
      pending: (id, next) => setReviewing(current => {
        const updated = { ...current };
        if (next) updated[id] = next;
        else delete updated[id];
        return updated;
      }),
      notify: (kind, message) => setNotification({ id: ++notificationId.current, kind, message }),
      confirmed,
      // A decision may finish after the user changes tabs; refresh that current
      // view rather than replacing it with the view where the request started.
      refresh: () => refreshCurrentView.current(),
    });
  }
  return { review, reviewing, notification, dismiss: () => setNotification(null) };
}
