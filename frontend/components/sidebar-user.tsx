function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

export function SidebarUser({ name, role }: { name: string; role: string }) {
  return (
    <div className="sidebar-user">
      <span className="sidebar-avatar" aria-hidden="true">{initials(name)}</span>
      <span className="sidebar-user-copy">
        <strong>{name}</strong>
        <small>{role}</small>
      </span>
    </div>
  );
}
