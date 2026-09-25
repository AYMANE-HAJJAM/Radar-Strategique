const EMPTY = "—";

export function formatDate(value: unknown): string {
  if (!value || value === EMPTY) return EMPTY;
  const source = String(value).slice(0, 10);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(source);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value);
}

export function formatDateTime(date: unknown, time?: unknown): string {
  const formatted = formatDate(date);
  if (formatted === EMPTY || !time) return formatted;
  return `${formatted} à ${String(time).slice(0, 5)}`;
}

function numeric(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const parsed = Number(value.replace(/\s/g, "").replace(",", "."));
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatMoney(value: unknown, currency = "MAD", compact = true): string {
  const amount = numeric(value);
  if (amount === null) return EMPTY;
  if (!compact) return `${new Intl.NumberFormat("fr-FR", {maximumFractionDigits:2}).format(amount)} ${currency}`;
  if (Math.abs(amount) >= 1_000_000) return `${new Intl.NumberFormat("fr-FR", {maximumFractionDigits:2}).format(amount/1_000_000)} M ${currency}`;
  if (Math.abs(amount) >= 1_000) return `${new Intl.NumberFormat("fr-FR", {maximumFractionDigits:0}).format(amount/1_000)} k ${currency}`;
  return `${new Intl.NumberFormat("fr-FR").format(amount)} ${currency}`;
}

export function formatStatus(review: unknown, discovery?: unknown): string {
  const value = String(review || "").toUpperCase();
  if (value === "PENDING") return String(discovery).toUpperCase() === "UPDATED" ? "Mis à jour" : "À traiter";
  if (value === "APPROVED" || value === "PERTINENT") return "Validé";
  if (value === "REJECTED") return "Rejeté";
  return "À traiter";
}

export function statusTone(review: unknown, discovery?: unknown): string {
  const label = formatStatus(review, discovery);
  return label === "Validé" ? "success" : label === "Rejeté" ? "danger" : label === "Mis à jour" ? "info" : "warning";
}

export function formatProcedure(value: unknown, announcement?: unknown): string {
  const raw = String(value || announcement || "").trim();
  if (!raw || raw.toLowerCase() === "unknown") return EMPTY;
  const normalized = raw.toLowerCase().replaceAll("_", " ");
  const labels: Record<string,string> = {
    "open tender": "Appel d’offres", "appel d'offres": "Appel d’offres", "appel d’offres": "Appel d’offres",
    "architectural competition": "Concours architectural", "concours": "Concours architectural",
    "consultation": "Consultation", "services": "Services",
  };
  return labels[normalized] || normalized.charAt(0).toUpperCase()+normalized.slice(1);
}

export function text(value: unknown): string { return value === null || value === undefined || value === "" ? EMPTY : String(value); }
