import type { Result } from "@/types";

const labels: Record<string, string> = {
  title: "Objet", institution: "Acheteur", reference: "Référence", publication_date: "Publication",
  deadline: "Échéance", deadline_time: "Heure limite", source_status: "Statut de l’offre",
  procedure_type: "Procédure", estimated_amount: "Estimation", estimated_currency: "Devise",
  estimated_amount_tax_mode: "Base fiscale", estimated_lots: "Lots",
  location_evidence: "Lieu", location: "Lieu", city_region: "Ville / région", territory: "Territoire",
  provisional_bond_amount: "Caution provisoire", provisional_bond_currency: "Devise de la caution",
  competition_prize_amount: "Prime du concours", competition_prize_currency: "Devise de la prime",
  eligibility_conditions: "Conditions d’éligibilité", competition_regulation_available: "Règlement disponible",
  document_types: "Documents",
};

function valueText(value: unknown, field: string): string {
  if (value === null || value === undefined || value === "") return "Non renseigné";
  if (typeof value === "boolean") return value ? "Oui" : "Non";
  if ((field === "deadline" || field === "publication_date") && typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [year, month, day] = value.split("-");
    return `${day}/${month}/${year}`;
  }
  if (Array.isArray(value)) return value.map(item => valueText(item, field)).join(", ") || "Aucun";
  if (typeof value === "object") return JSON.stringify(value);
  if (typeof value === "number") return value.toLocaleString("fr-FR");
  return String(value);
}

export function PreviousReview({ item }: { item: Result }) {
  if (item.review_status !== "PENDING" || !item.previous_review_status) return null;
  return <small className="previous-review">{item.previous_review_status === "APPROVED" ? "Validé auparavant" : "Rejeté auparavant"}</small>;
}

export function ReviewChanges({ item }: { item: Result }) {
  if (item.review_status !== "PENDING" || !item.previous_review_status || !item.review_changes?.length) return null;
  return <details className="review-changes">
    <summary>Modifications ({item.review_changes.length})</summary>
    <div>Modifications depuis {item.previous_review_status === "APPROVED" ? "la dernière validation" : "le dernier rejet"} :</div>
    <ul>{item.review_changes.map(change => <li key={change.field}>
      <strong>{labels[change.field] || change.field} :</strong> {valueText(change.before, change.field)} → {valueText(change.after, change.field)}
    </li>)}</ul>
  </details>;
}
