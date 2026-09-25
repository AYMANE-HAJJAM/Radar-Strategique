"use client";
import { usePathname } from "next/navigation";
import { DashboardIcon, LogoutIcon, RadarIcon, SearchIcon, UsersIcon } from "@/components/nav-icons";
import { SidebarNavItem } from "@/components/sidebar-nav-item";
import { SidebarUser } from "@/components/sidebar-user";
import { RADARS } from "@/lib/radars";
import type { User } from "@/types";

function radarActive(path: string, id: string) {
  return path === `/radars/${id}` || path.startsWith(`/radars/${id}/`);
}

export function Sidebar({ user, open, onClose, onLogout }: { user: User | null; open: boolean; onClose: () => void; onLogout: () => void }) {
  const path = usePathname();
  return (
    <aside className={`sidebar${open ? " open" : ""}`} id="app-sidebar" aria-label="Navigation de l’application">
      <div className="sidebar-brand">
        <span>Radar stratégique</span>
        <button type="button" className="sidebar-close" aria-label="Fermer le menu" onClick={onClose}>Fermer</button>
      </div>
      {user && <SidebarUser name={user.name} role={user.role} />}
      <nav className="sidebar-nav" aria-label="Navigation principale">
        <SidebarNavItem href="/" label="Tableau de bord" icon={<DashboardIcon />} active={path === "/"} onNavigate={onClose} />
        <div className="nav-section">Radars</div>
        {RADARS.map((radar) => (
          <SidebarNavItem key={radar.id} href={`/radars/${radar.id}`} label={`Radar ${radar.id}`} hint={radar.name} icon={<RadarIcon />} active={radarActive(path, radar.id)} onNavigate={onClose} />
        ))}
        <div className="nav-divider" />
        <SidebarNavItem href="/targeted-search" label="Recherche ciblée" icon={<SearchIcon />} active={path.startsWith("/targeted-search")} onNavigate={onClose} />
        {user?.role === "ADMIN" && <SidebarNavItem href="/admin/users" label="Utilisateurs & accès" icon={<UsersIcon />} active={path.startsWith("/admin/users")} onNavigate={onClose} />}
      </nav>
      <div className="sidebar-footer">
        <button type="button" className="logout-button" onClick={onLogout}>
          <LogoutIcon />
          Déconnexion
        </button>
      </div>
    </aside>
  );
}
