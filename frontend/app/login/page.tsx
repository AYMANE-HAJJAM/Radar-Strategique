"use client";
import {FormEvent,useState} from "react";
import {useRouter} from "next/navigation";
import {auth} from "@/lib/api";

export default function Login(){
  const router=useRouter();const[error,setError]=useState("");const[busy,setBusy]=useState(false);
  async function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();setBusy(true);setError("");const form=new FormData(event.currentTarget);try{await auth.access(String(form.get("access_code")));router.push("/");router.refresh()}catch(reason){setError(reason instanceof Error?reason.message:"Connexion impossible")}finally{setBusy(false)}}
  return <main className="login"><form className="panel" onSubmit={submit}><div className="eyebrow">Accès interne</div><h1>Radar stratégique</h1><label htmlFor="access_code">Code d’accès</label><input id="access_code" name="access_code" autoComplete="off" placeholder="XXXX-XXXX-XX" maxLength={12} required autoFocus/>{error&&<p className="error">{error}</p>}<button className="button" disabled={busy} style={{width:"100%",marginTop:20}}>{busy?"Connexion au serveur…":"Accéder"}</button></form></main>
}
