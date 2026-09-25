import Link from "next/link";
import { launcherName, runStatusLabel } from "@/components/run-status-banner";
import type { Run } from "@/types";

export function RunHistoryTable({ radarId, runs }: { radarId: string; runs: Run[] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Date</th><th>Statut</th><th>Résultats</th><th>Lancée par</th></tr></thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id}>
              <td>
                <Link href={`/radars/${radarId}?run_id=${run.id}`}>{new Date(run.started_at).toLocaleString("fr-FR")}</Link>
                <small className="run-id">#{run.id}</small>
              </td>
              <td><span className="badge">{runStatusLabel(run.status)}</span></td>
              <td>{run.new_results_count} nouveau{run.new_results_count === 1 ? "" : "x"} · {run.updated_results_count} mis à jour</td>
              <td>{launcherName(run, "—")}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
