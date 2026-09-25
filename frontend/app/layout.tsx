import "./globals.css";
import "./auth.css";
import "./results.css";
import "./shell.css";
import { AppShell } from "@/components/app-shell";

export const metadata = {
  title: "Radar stratégique",
  description: "Veille interne",
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body suppressHydrationWarning>
        <div className="shell">
          <AppShell>{children}</AppShell>
        </div>
      </body>
    </html>
  );
}
