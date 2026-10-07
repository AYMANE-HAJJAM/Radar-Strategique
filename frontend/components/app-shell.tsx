"use client";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { MainContent } from "@/components/main-content";
import { Sidebar } from "@/components/sidebar";
import { State } from "@/components/state";
import { auth, ApiError, AUTH_CHANGE_KEY, AUTH_EXPIRED_EVENT } from "@/lib/api";
import type { User } from "@/types";

type SessionCheck = { path: string; user: User | null; error?: string };

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<SessionCheck | null>(null);
  const [openPath, setOpenPath] = useState<string | null>(null);
  const generation = useRef(0);
  const loggingOut = useRef(false);
  const recheck = useRef<() => void>(() => {});
  const open = openPath === path;

  useEffect(() => {
    let cancelled = false;
    async function check(background = false) {
      if (loggingOut.current) return;
      const request = ++generation.current;
      if (!background) setSession(null);
      try {
        const result = await auth.me();
        if (cancelled || request !== generation.current) return;
        setSession({ path, user: result.user });
        if (path === "/login") router.replace("/");
      } catch (reason) {
        if (cancelled || request !== generation.current) return;
        if (reason instanceof ApiError && reason.status === 401) {
          setSession({ path, user: null });
          if (path !== "/login") router.replace("/login");
        } else {
          setSession({ path, user: null, error: reason instanceof Error ? reason.message : "Connexion impossible" });
        }
      }
    }
    function onStorage(event: StorageEvent) {
      if (event.key === AUTH_CHANGE_KEY || event.key === null) void check();
    }
    function onPageShow(event: PageTransitionEvent) {
      if (event.persisted) void check(true);
    }
    function onExpired() {
      ++generation.current;
      setSession({ path, user: null });
      if (path !== "/login") router.replace("/login");
    }
    recheck.current = check;
    void check();
    window.addEventListener("pageshow", onPageShow);
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    window.addEventListener("storage", onStorage);
    return () => {
      cancelled = true;
      window.removeEventListener("pageshow", onPageShow);
      window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
      window.removeEventListener("storage", onStorage);
    };
  }, [path, router]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) { if (event.key === "Escape") setOpenPath(null); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function logout() {
    loggingOut.current = true;
    ++generation.current;
    setSession(null);
    setOpenPath(null);
    try {
      await auth.logout();
      loggingOut.current = false;
      // Ignore checks that started before logout completed.
      ++generation.current;
      setSession(null);
      router.replace("/login");
      router.refresh();
    } catch (reason) {
      loggingOut.current = false;
      ++generation.current;
      setSession({ path, user: null, error: reason instanceof Error ? reason.message : "Déconnexion impossible" });
    }
  }

  if (!session || session.path !== path) return <State>Connexion au serveur…</State>;
  if (session.error) return <State error>{session.error}<button className="button" onClick={() => recheck.current()}>Réessayer</button></State>;
  if (path === "/login") return session.user ? <State>Redirection…</State> : children;
  if (!session.user) return <State>Redirection…</State>;

  return (
    <div className="app-shell">
      <button type="button" className={`sidebar-backdrop${open ? " visible" : ""}`} aria-label="Fermer le menu" tabIndex={open ? 0 : -1} onClick={() => setOpenPath(null)} />
      <Sidebar user={session.user} open={open} onClose={() => setOpenPath(null)} onLogout={logout} />
      <MainContent menuOpen={open} onOpenMenu={() => setOpenPath(path)}>{children}</MainContent>
    </div>
  );
}
