import Link from "next/link";

export function SidebarNavItem({ href, label, hint, icon, active, onNavigate }: { href: string; label: string; hint?: string; icon: React.ReactNode; active: boolean; onNavigate: () => void }) {
  return (
    <Link className={`nav-item${active ? " active" : ""}`} href={href} aria-current={active ? "page" : undefined} onClick={onNavigate}>
      <span className="nav-icon">{icon}</span>
      <span className="nav-copy">
        <span className="nav-label">{label}</span>
        {hint && <span className="nav-hint">{hint}</span>}
      </span>
    </Link>
  );
}
