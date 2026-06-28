import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Shield } from "lucide-react";
import { cn } from "./ui";
import { api } from "../api/client";

const links = [
  { to: "/", label: "Overview", end: true },
  { to: "/governance", label: "Governance" },
  { to: "/policy", label: "Policy" },
  { to: "/audit", label: "Audit" },
];

export function Layout() {
  const { data: config } = useQuery({
    queryKey: ["config"],
    queryFn: api.config,
    staleTime: 60_000,
  });
  const hermesChatUrl = config?.hermes_chat_url ?? "http://127.0.0.1:9119/chat";

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-800 bg-slate-950/90 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-center gap-3">
            <Shield className="h-7 w-7 text-brand" />
            <div>
              <div className="text-sm font-semibold uppercase tracking-wider text-brand">
                IntentFrame
              </div>
              <div className="text-lg font-semibold text-white">Control Plane</div>
            </div>
          </div>
          <a
            href={hermesChatUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-900"
          >
            Hermes chat
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
        <nav className="mx-auto flex max-w-6xl gap-1 px-6 pb-3">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) =>
                cn(
                  "rounded-md px-3 py-2 text-sm font-medium transition",
                  isActive
                    ? "bg-slate-800 text-white"
                    : "text-slate-400 hover:bg-slate-900 hover:text-slate-200",
                )
              }
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
    </div>
  );
}
