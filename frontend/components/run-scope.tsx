import Link from "next/link";

export function formatRunStamp(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${pad(date.getDate())}/${pad(date.getMonth() + 1)}/${date.getFullYear()} à ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function discoveryLabel(observation?: string | null, discovery?: string) {
  const state = (observation || "").toLowerCase();
  if (state === "updated") return "Mis à jour";
  if (state === "new") return "Nouveau";
  return String(discovery || "").toUpperCase() === "UPDATED" ? "Mis à jour" : "Nouveau";
}

export function DiscoveryBadge({ observation, discovery }: { observation?: string | null; discovery?: string }) {
  const label = discoveryLabel(observation, discovery);
  return <span className={`status-badge ${label === "Mis à jour" ? "info" : "warning"}`}>{label}</span>;
}

function countText(value: number | null) {
  return value === null ? "…" : String(value);
}

export function RunScopeSwitch({ runCount, backlogCount, runHref, backlogHref, runActive }: {
  runCount: number | null; backlogCount: number | null; runHref: string; backlogHref: string; runActive: boolean;
}) {
  return (
    <nav className="scope-switch" aria-label="Portée des résultats">
      <Link className={runActive ? "active" : ""} href={runHref} aria-current={runActive ? "page" : undefined}>Cette recherche ({countText(runCount)})</Link>
      <Link className={runActive ? "" : "active"} href={backlogHref} aria-current={runActive ? undefined : "page"}>Tous à traiter ({countText(backlogCount)})</Link>
    </nav>
  );
}

export function RunContext({ id, startedAt, launcher }: { id: string | number; startedAt?: string | null; launcher?: string | null }) {
  return (
    <div className="run-context">
      <strong>Recherche #{id}</strong>
      {startedAt ? <span>{formatRunStamp(startedAt)}</span> : null}
      <span>Lancée par {launcher || "—"}</span>
    </div>
  );
}

export function RunEmpty({ href }: { href: string }) {
  return (
    <div className="table-state">
      <strong>Aucun nouveau résultat à traiter pour cette recherche.</strong>
      <Link className="run-empty-link" href={href}>Voir tous les résultats à traiter</Link>
    </div>
  );
}
