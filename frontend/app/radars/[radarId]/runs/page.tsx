"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { RunHistoryTable } from "@/components/run-history-table";
import { State } from "@/components/state";
import { TopContextBar } from "@/components/top-context-bar";
import { api } from "@/lib/api";
import { radarName } from "@/lib/radars";
import type { Page, Run } from "@/types";

export default function Runs() {
  const { radarId } = useParams<{ radarId: string }>();
  const [data, setData] = useState<Page<Run> | null>(null);
  useEffect(() => { api<Page<Run>>(`/radars/${radarId}/runs?page_size=50`).then(setData); }, [radarId]);
  return (
    <>
      <TopContextBar crumb={<><Link href={`/radars/${radarId}`}>Radar {radarId}</Link> / {radarName(radarId)}</>} title="Recherches précédentes" />
      <main className="container">
        {!data ? <State>Connexion au serveur…</State> : data.items.length === 0 ? <State>Aucune recherche précédente.</State> : <RunHistoryTable radarId={radarId} runs={data.items} />}
      </main>
    </>
  );
}
