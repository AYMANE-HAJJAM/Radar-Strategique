# Radar 1 PMMP full-crawl validation

**When:** 2026-10-02, 18:24–18:42 UTC+1 (17:24:09–17:42:13 UTC)  
**Scope:** Non-production. `new_pmmp_collector(mode='full')` against the public consultations-en-cours board. No production switch, no policy change, no paid search, no model call, no writes to Radar 1 `results` or `result_observations`.

The crawl followed the collector as implemented: GET the consultations-en-cours form, POST “Lancer la recherche”, then follow the Prado next control until the site reports the last page. Listings stayed in the process that ran the crawl. They were not inserted into the business tables.

---

## Crawl result

| Measure | Value |
|---|---|
| Pages visited | **383** |
| Listings collected | **3,821** |
| Unique listings | **3,820** |
| Duplicates | **1** |
| PMMP declared results | 3,821 |
| PMMP declared pages | 383 |
| Stop reason | **`final_page`** |
| Last page | **383**, 1 row, `has_next` false |
| HTTP requests that succeeded | 384 (1 form GET, 1 search POST, 382 next-page POSTs) |
| HTTP retries | **0** |
| HTTP errors | **0** |
| Parser exceptions | **0** |
| Rows missing reference, title, or consultation id | **0** |
| Elapsed time | **1,084.1 seconds** (18 min 4 s) |

Row arithmetic matches the board: 382 pages of 10 plus a final page of 1 equals 3,821, which is the count PMMP printed (`nombreElement` / `nombrePageTop`).

First-page fingerprint (digest of that page’s listing fingerprints, consultation ids, and references, in order):

`f691bdcd41b5f785b759997e4f41b67da3b561f87d2a3b5de9aa7a50b66826e9`

Page 1 ran from consultation id `1040952` (`81/2026/DR9`) through `1045092` (`12/2026`). Page 383 held one listing: consultation id `1038205`, reference `170/O/26`, fingerprint `0c7577f3b3f7658aee5265836749c942e32ee4b52a040e6efd1c218f8df0b646`.

The one duplicate is the same notice twice, on consecutive pages, not a second consultation. Consultation id `1042496` / organization `d4q`, reference `37/DRC/CI/2026`, “RENOUVELLEMENT DES MOTEURS 5,5KV…”, appears on page 71 and again on page 72. The collector kept the first as `NEW` and marked the second `DUPLICATE`. Outcome counts: 3,820 `NEW`, 1 `DUPLICATE`, 0 `UPDATED` (the index started empty).

Listing cells still carry the portal’s own truncation suffix (` - ...` on references, ` ...` on titles). Buyers often end with a trailing dash. Location was empty on the sampled rows. Every sampled row still has a consultation id, a reference, a title, a buyer, a deadline, a procedure, and a detail URL. That is a field-cleaning task for persistence, not a missing page.

---

## Notice 04/2026/AUS

**FOUND.**

| Field | Collected value |
|---|---|
| Page | 378 |
| PMMP consultation id | `1036481` |
| Organization | `j8k` |
| Reference | `04/2026/AUS` (listing text `04/2026/AUS - ...`) |
| Title / object | Appel d’offres ouvert National n° 04/2026 ayant pour objet l’étude de valorisation du patrimoine culturel, naturel et historique de la province de Settat. |
| Buyer | Agence urbaine de Settat |
| Deadline | 02/10/2026 11:00 |
| Publication | 03/09/2026 |
| Procedure | Appel d'offres ouvert |
| Category | Services |
| Detail URL | `https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1036481&orgAcronyme=j8k` |

The object text contains both “valorisation du patrimoine culturel, naturel et historique” and “province de Settat”.

---

## Heritage wording on the board

Accent-insensitive substring match on title and reference. A listing can match more than one term. These are not relevance decisions.

| Term | Listings |
|---|---:|
| patrimoine | 5 |
| médina | 11 |
| monument | 1 |
| remparts | 0 |
| restauration | 63 |
| conservation | 1 |
| valorisation | 38 |
| fortification | 0 |
| historique | 4 |
| concours architectural | 2 |
| études architecturales | 44 |

**165** unique listings match at least one of those terms. `remparts` and `fortification` did not appear. `restauration` and `valorisation` include catering, waste, and similar wording, which is why the counts stay unclassified.

Twenty examples, as collected:

| Page | Reference | Consultation id | Object (as listed) | Buyer | Deadline |
|---|---|---|---|---|---|
| 21 | 23/DDE/DDI/2026 | 1040455 | Maintenance et support logiciel du système de gestion du patrimoine foncier et immobilier de l’Etat AMLACS | Directeur des domaines | 29/10/2026 10:00 |
| 77 | 43/CS/2026 | 1032849 | Prestations topographiques, dossiers techniques cadastraux des terrains appartenant au patrimoine de la commune de Settat | Commune urbaine de Settat | 22/10/2026 11:00 |
| 262 | 22/2026/DRATTH/DPAD | 1008606 | Étude de caractérisation de trois sites potentiels des Systèmes Ingénieux du Patrimoine Agricole Marocain (SIPAM), Tanger-Tétouan-Al Hoceima | Direction régionale de l’agriculture | 12/10/2026 10:00 |
| 62 | 90/INV/TNG/2026 | 1044763 | Extension de 9 salles de classe, lycée collégial, commune Tanger Medina | Direction provinciale de l’éducation, Tanger-Assilah | 23/10/2026 12:00 |
| 72 | 03/2026 | 1042105 | Élaboration du plan d’aménagement et de sauvegarde de la médina de Tiznit | Agence urbaine de Taroudannt | 22/10/2026 11:30 |
| 185 | 145/2026 | 1039623 | Études techniques, suivi et direction des travaux de réhabilitation et de mise en valeur de la médina de Safi | Al Omrane Marrakech-Safi | 15/10/2026 10:00 |
| 45 | 12/DRCRMS/2026 | 1020823 | Sécurité, surveillance et gardiennage des bâtiments administratifs et monuments historiques, Essaouira et Marrakech-Safi | Direction régionale des affaires culturelles, Marrakech-Safi | 27/10/2026 10:00 |
| 3 | 48/RH/2026/EXP | 1045131 | Restauration au profit des internats et cantines, Rhamna | Direction provinciale de l’éducation, Rhamna | 12/11/2026 10:00 |
| 4 | 054/2026/CHUMVIO | 1045559 | Restauration collective, Centre hospitalier universitaire Mohammed VI d’Oujda | CHU Mohammed VI Oujda | 12/11/2026 10:00 |
| 126 | 08/2026/DRACS | 1030316 | Schéma directeur régional pour la conservation des eaux et des sols, Casablanca-Settat | Direction régionale de l’agriculture, Casablanca-Settat | 20/10/2026 10:00 |
| 10 | 01/2026 | 1031023 | Gestion déléguée du centre d’enfouissement et de valorisation des déchets « Saddina pour l’Environnement » | Groupement de communes Seddina pour environnement | 04/11/2026 11:00 |
| 18 | 30/2026/DPA/G | 1037318 | Matériel pour une unité de valorisation des dattes, Guelmim | Direction provinciale de l’agriculture, Guelmim | 29/10/2026 11:00 |
| 25 | 1/2026 | 1037198 | Assistance à la valorisation de l’Observatoire régional de développement intégré de Rabat-Salé-Kénitra | Inspection régionale de l’urbanisme | 28/10/2026 11:00 |
| 210 | 04/DRCSM/2026 | 1034902 | Sécurité et gardiennage des sites archéologiques et historiques, Souss-Massa | Direction régionale de la culture, Souss-Massa | 14/10/2026 10:00 |
| 378 | 04/2026/AUS | 1036481 | Étude de valorisation du patrimoine culturel, naturel et historique de la province de Settat | Agence urbaine de Settat | 02/10/2026 11:00 |
| 2 | 06/2026 | 1040198 | Concours architectural, nouveau siège de la direction régionale de l’équipement, Laâyoune | Direction régionale de l’équipement, Laâyoune | 17/11/2026 11:00 |
| 12 | 06/2026/CA/BR/RGON | 1037536 | Concours architectural, annexe du siège de la région Guelmim-Oued Noun | Région de Guelmim-Oued Noun | 03/11/2026 11:00 |
| 15 | 101/2026/OFPPT | 1041342 | Études architecturales et conduite des travaux de démolition et reconstruction de l’ISTA Tahannaout et son internat | OFPPT | 02/11/2026 10:00 |
| 38 | 39/RDOE/2026 | 1041080 | Études architecturales et suivi des travaux de création d’une gare routière à Bir Gandouz | Région de Oued Eddahab | 27/10/2026 10:30 |
| 59 | CA22/AREFCS/2026 | 1045437 | Études architecturales et suivi des travaux de construction du lycée qualifiant Al Imame Al Ghazali, Bir Jdid | AREF Casablanca-Settat | 26/10/2026 10:00 |

---

## Comparison with Radar 1 run #41

Run #41 (2026-10-02 09:31–09:37 UTC, completed, launched by user 1) is the latest production keyword run. It used direct keyword pages, not this board walk. From that run’s stored metadata:

| | Run #41 legacy discovery | This full crawl |
|---|---:|---:|
| PMMP listings seen | **81** observations (`pmmp_observations`) | **3,820** unique, from **3,821** rows |
| Pages | 17 PMMP keyword pages, about 10 rows each, then a 100-observation cap | 383 pages, through the declared last page |
| 04/2026/AUS | Not in the 100 trace events. The keyword `etude valorisation patrimoine culturel` ran and its only new row was the ISPITS Casablanca rehabilitation | **Present, page 378** |

Run #41 handed one keeper to persistence, `101/2026/OFPPT` (ISTA Tahannaout), and recorded it UNCHANGED. That notice is on page 15 of this crawl (consultation id `1041342`). The two concours the keyword run did see and then rejected (`06/2026`, `06/2026/CA/BR/RGON`) are on pages 2 and 12 here. The board also contains notices the keyword run never opened, including the Settat study and the médina de Tiznit plan (`03/2026`, page 72, consultation id `1042105`).

---

## Conclusion

**A. Full PMMP collector coverage is valid and ready for persistence work.**

The crawl stopped because page 383 had no next link, after 383 pages and 3,821 rows, equal to the counts the board itself declared. There were no HTTP failures and no parser exceptions. `04/2026/AUS`, absent from run #41, was collected on page 378. Persistence can start from this crawl shape. Before any save, strip the listing-cell ellipsis, decide where the baseline index lives (not in the review tables), and keep the keyword path until that comparison is accepted. This run did not write the business tables and did not change Radar 1 runtime.
