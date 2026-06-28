import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

export function cn(...parts: Array<string | false | undefined>) {
  return clsx(parts);
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border border-slate-800 bg-slate-900/80 p-5 shadow-lg", className)}>
      {children}
    </div>
  );
}

export function Badge({
  ok,
  label,
}: {
  ok: boolean;
  label: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        ok ? "bg-emerald-500/15 text-emerald-300" : "bg-rose-500/15 text-rose-300",
      )}
    >
      {label}
    </span>
  );
}

export function Button({
  className,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
}) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variant === "primary" && "bg-brand text-slate-950 hover:bg-cyan-300",
        variant === "secondary" && "border border-slate-700 bg-slate-800 hover:bg-slate-700",
        variant === "danger" && "bg-rose-600 text-white hover:bg-rose-500",
        className,
      )}
      {...props}
    />
  );
}

export function PageHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl font-semibold tracking-tight text-white">{title}</h1>
      {description ? <p className="mt-1 text-sm text-slate-400">{description}</p> : null}
    </div>
  );
}

export function Alert({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" }) {
  return (
    <div
      className={cn(
        "mb-4 rounded-lg border px-4 py-3 text-sm",
        tone === "info" && "border-cyan-800/60 bg-cyan-950/40 text-cyan-100",
        tone === "warn" && "border-amber-800/60 bg-amber-950/40 text-amber-100",
      )}
    >
      {children}
    </div>
  );
}
