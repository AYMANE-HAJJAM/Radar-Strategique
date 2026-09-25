type IconProps = { className?: string };

function Icon({ children, className }: IconProps & { children: React.ReactNode }) {
  return (
    <svg className={className} viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

export function DashboardIcon() {
  return <Icon><rect x="2" y="2" width="5" height="5" rx="1" /><rect x="9" y="2" width="5" height="5" rx="1" /><rect x="2" y="9" width="5" height="5" rx="1" /><rect x="9" y="9" width="5" height="5" rx="1" /></Icon>;
}

export function RadarIcon() {
  return <Icon><circle cx="8" cy="8" r="5.25" /><circle cx="8" cy="8" r="1.4" fill="currentColor" stroke="none" /></Icon>;
}

export function SearchIcon() {
  return <Icon><circle cx="7" cy="7" r="4.25" /><path d="M10.4 10.4 13.5 13.5" /></Icon>;
}

export function UsersIcon() {
  return <Icon><circle cx="6" cy="5.2" r="2" /><path d="M2.8 12.4c.4-1.8 1.7-2.7 3.2-2.7s2.8.9 3.2 2.7" /><circle cx="11" cy="5.6" r="1.5" /><path d="M10.2 9.8c1.2.2 2.1.9 2.5 2.2" /></Icon>;
}

export function LogoutIcon() {
  return <Icon><path d="M6.5 3.2H3.8v9.6h2.7" /><path d="M7 8h6" /><path d="M10.6 5.4 13.2 8l-2.6 2.6" /></Icon>;
}

export function MenuIcon() {
  return <Icon><path d="M2.5 4.2h11M2.5 8h11M2.5 11.8h11" /></Icon>;
}
