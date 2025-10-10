import { cn } from "@/lib/utils";

export function StatCard({ value, label, hint, trend, className }: { value: string | number; label: string; hint?: string; trend?: "up"|"down"|null; className?: string; }) {
  return (
    <div className={cn("card-surface p-6", className)} aria-label={`${label} statistic`}>
      <div className="flex items-start justify-between">
        <div className="text-[3em] leading-none font-extrabold text-[#111827]">{value}</div>
        {trend && (
          <span className={cn("pill", trend === "up" ? "bg-success text-white" : "bg-warning text-white")} aria-label={`trend ${trend}`}>{trend === "up" ? "▲" : "▼"}</span>
        )}
      </div>
      <div className="mt-2 text-sm text-[#6b7280]">{label}</div>
      {hint && <div className="mt-1 text-xs text-[#6b7280]">{hint}</div>}
    </div>
  );
}
