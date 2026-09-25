"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { TopContextBar } from "@/components/top-context-bar";
import { State } from "@/components/state";
import { api, ApiError } from "@/lib/api";
import { RADARS } from "@/lib/radars";
import type { Radar } from "@/types";

export default function Dashboard() {
  const router = useRouter();
  const [data, setData] = useState<Radar[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<{ items: Radar[] }>("/radars").then((result) => setData(result.items)).catch((reason) => {
      if (reason instanceof ApiError && reason.status === 401) router.push("/login");
      else setError(reason instanceof Error ? reason.message : "Erreur");
    });
  }, [router]);
  const pending = data?.reduce((sum, radar) => sum + radar.pending_count, 0) ?? 0;
  const running = data?.filter((radar) => radar.last_run && ["initialized", "running"].includes(radar.last_run.status)).length ?? 0;
  return (
    <>
      <TopContextBar crumb="Vue d’ensemble" title="Tableau de bord" description="Les signaux à examiner et l’état des dernières recherches." />
      <main className="container">
        {error ? <State error>{error}</State> : !data ? <State>Connexion au serveur…</State> : (
          <>
            <div className="summary-row">
              <div className="panel summary-stat"><strong>{pending}</strong><span>à traiter</span></div>
              <div className="panel summary-stat"><strong>{running}</strong><span>recherche{running === 1 ? "" : "s"} en cours</span></div>
              <div className="panel summary-stat"><strong>{data.length}</strong><span>radars</span></div>
            </div>
            <div className="grid">
              {data.map((radar) => {
                const name = RADARS.find((item) => item.id === String(radar.id))?.name || radar.name;
                return (
                  <Link className="card" href={`/radars/${radar.id}`} key={radar.id}>
                    <div className="card-top">
                      <span className="eyebrow">Radar {radar.id}</span>
                      <span className={`badge ${radar.last_run?.status === "running" ? "running" : ""}`}>{radar.last_run?.status || "Jamais lancé"}</span>
                    </div>
                    <h2>{name}</h2>
                    <p className="muted">{radar.description}</p>
                    <div className="count">{radar.pending_count}</div>
                    <span className="muted">résultat{radar.pending_count === 1 ? "" : "s"} à traiter</span>
                    {radar.last_run?.started_at && <span className="run-time">Dernière recherche · {new Date(radar.last_run.started_at).toLocaleString("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" })}</span>}
                  </Link>
                );
              })}
              <Link className="card" href="/targeted-search">
                <div className="eyebrow">À la demande</div>
                <h2>Recherche ciblée</h2>
                <p className="muted">Décrivez un besoin précis, confirmez le brief et lancez une recherche bornée.</p>
                <span className="link">Commencer →</span>
              </Link>
            </div>
          </>
        )}
      </main>
    </>
  );
}
