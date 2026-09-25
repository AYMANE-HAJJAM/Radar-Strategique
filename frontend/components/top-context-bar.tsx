export function TopContextBar({ crumb, title, description, actions }: { crumb?: React.ReactNode; title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <header className="context-bar">
      <div className="context-copy">
        {crumb && <div className="context-crumb">{crumb}</div>}
        <h1>{title}</h1>
        {description && <p className="context-description">{description}</p>}
      </div>
      {actions && <div className="context-actions">{actions}</div>}
    </header>
  );
}
