import type { Run } from "@/types";

export function isActiveRun(run: Run | null) {
  return !!run && ["initialized", "running"].includes(run.status);
}

type Options = {
  currentRun: () => Run | null;
  requestRun: (id: number) => Promise<Run>;
  updateRun: (run: Run) => void;
  refreshResults: () => Promise<unknown>;
  onError: (reason: unknown) => void;
  document: Pick<Document, "visibilityState" | "addEventListener" | "removeEventListener">;
  window: Pick<Window, "addEventListener" | "removeEventListener">;
};

// This observer only reads a reserved run. Launching remains a user action.
export function startRadarRunSync(options: Options) {
  let disposed = false;
  let inFlight = false;
  let refreshQueued = false;
  let lastRestore = -Infinity;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const visible = () => options.document.visibilityState !== "hidden";

  async function refresh(restored = false) {
    if (disposed || !visible()) return;
    if (inFlight) {
      if (restored) refreshQueued = true;
      return;
    }
    const previous = options.currentRun();
    if (!restored && !isActiveRun(previous)) return;
    inFlight = true;
    try {
      if (previous) {
        const next = await options.requestRun(previous.id);
        if (disposed) return;
        // A launch or route change may have replaced the run during this GET.
        if (options.currentRun()?.id !== previous.id) return;
        options.updateRun(next);
        if (restored || !isActiveRun(next)) await options.refreshResults();
      } else if (restored) {
        await options.refreshResults();
      }
    } catch (reason) {
      if (!disposed) options.onError(reason);
    } finally {
      inFlight = false;
      if (refreshQueued && !disposed) {
        refreshQueued = false;
        void refresh(true);
      }
    }
  }

  function schedule() {
    clearTimeout(timer);
    if (disposed || !visible()) return;
    timer = setTimeout(async () => {
      await refresh();
      schedule();
    }, 3000);
  }
  function restore() {
    if (!visible() || disposed) return;
    // Browsers commonly send visibilitychange and focus together.
    const now = Date.now();
    if (now - lastRestore < 250) return;
    lastRestore = now;
    void refresh(true);
    schedule();
  }
  function visibilityChanged() {
    if (visible()) restore();
    else { clearTimeout(timer); lastRestore = -Infinity; }
  }
  function pageShown(event: Event) {
    if ((event as PageTransitionEvent).persisted) restore();
  }

  options.document.addEventListener("visibilitychange", visibilityChanged);
  options.window.addEventListener("focus", restore);
  options.window.addEventListener("pageshow", pageShown);
  schedule();
  return () => {
    disposed = true;
    clearTimeout(timer);
    options.document.removeEventListener("visibilitychange", visibilityChanged);
    options.window.removeEventListener("focus", restore);
    options.window.removeEventListener("pageshow", pageShown);
  };
}
