import type { Run } from "@/types";

export function runStatusLabel(status: string) {
  if (status === "failed") return "Échec";
  if (status === "completed") return "Terminée";
  return "En cours";
}

export function launcherName(run: Pick<Run, "launched_by">, anonymous = "Utilisateur non identifié") {
  return run.launched_by?.name || anonymous;
}

export function RunStatusBanner({ run }: { run: Run }) {
  return (
    <div className="run-banner" role="status">
      <div className="run-banner-title"><span className="status-dot" />Recherche #{run.id} · {runStatusLabel(run.status)}</div>
      <div className="run-launcher">Lancée par : {launcherName(run)}</div>
    </div>
  );
}
