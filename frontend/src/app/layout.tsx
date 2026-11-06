import "./globals.css";
import Link from "next/link";
import type { ReactNode } from "react";

export const metadata = { title: "Supervisor Argus", description: "Qualificação de ligações em tempo real" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <header className="border-b border-slate-800 px-6 py-3 flex items-center gap-6">
          <span className="font-semibold">🎧 Supervisor Argus</span>
          <Link href="/" className="text-sm text-slate-300 hover:text-white">Dashboard</Link>
          <Link href="/calls" className="text-sm text-slate-300 hover:text-white">Ligações</Link>
        </header>
        <main className="p-6 max-w-[1400px] mx-auto">{children}</main>
      </body>
    </html>
  );
}
