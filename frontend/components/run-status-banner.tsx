import type { Run } from "@/types";

export function runStatusLabel(status: string) {
  if (status === "failed") return "Échec";
  if (status === "completed") return "Terminée";
  return "En cours";
}

export function launcherName(run: Pick<Run, "launched_by">, anonymous = "Utilisateur non identifié") {
  return run.launched_by?.name || anonymous;
}
