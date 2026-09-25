"use client";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { MainContent } from "@/components/main-content";
import { Sidebar } from "@/components/sidebar";
import { auth } from "@/lib/api";
import type { User } from "@/types";

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [openPath, setOpenPath] = useState<string | null>(null);
  const open = openPath === path;

  useEffect(() => {
    if (path === "/login") return;
    let cancelled = false;
    auth.me().then((result) => { if (!cancelled) setUser(result.user); }).catch(() => { if (!cancelled) router.push("/login"); });
    return () => { cancelled = true; };
  }, [path, router]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) { if (event.key === "Escape") setOpenPath(null); }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function logout() {
    await auth.logout();
    setUser(null);
    setOpenPath(null);
    router.push("/login");
    router.refresh();
  }

  if (path === "/login") return children;

  return (
    <div className="app-shell">
      <button type="button" className={`sidebar-backdrop${open ? " visible" : ""}`} aria-label="Fermer le menu" tabIndex={open ? 0 : -1} onClick={() => setOpenPath(null)} />
      <Sidebar user={user} open={open} onClose={() => setOpenPath(null)} onLogout={logout} />
      <MainContent menuOpen={open} onOpenMenu={() => setOpenPath(path)}>{children}</MainContent>
    </div>
  );
}
