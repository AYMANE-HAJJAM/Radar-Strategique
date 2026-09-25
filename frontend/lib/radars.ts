export const RADARS = [
  { id: "1", name: "Marchés" },
  { id: "2", name: "Projets en gestation" },
  { id: "3", name: "Décideurs & Institutions" },
  { id: "4", name: "Politiques publiques" },
  { id: "5", name: "Financements" },
] as const;

export function radarName(id: string): string {
  return RADARS.find((radar) => radar.id === id)?.name ?? "Radar";
}
