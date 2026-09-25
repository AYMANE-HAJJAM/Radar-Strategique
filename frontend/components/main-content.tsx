import { MenuIcon } from "@/components/nav-icons";

export function MainContent({ children, menuOpen, onOpenMenu }: { children: React.ReactNode; menuOpen: boolean; onOpenMenu: () => void }) {
  return (
    <div className="main-content">
      <div className="mobile-bar">
        <button type="button" className="menu-button" aria-label="Ouvrir le menu" aria-expanded={menuOpen} aria-controls="app-sidebar" onClick={onOpenMenu}>
          <MenuIcon />
          <span>Menu</span>
        </button>
      </div>
      {children}
    </div>
  );
}
