const styles: Record<string, string> = {
  sent: "bg-emerald-100 text-emerald-800",
  ok: "bg-emerald-100 text-emerald-800",
  pending: "bg-amber-100 text-amber-800",
  partial: "bg-amber-100 text-amber-800",
  skipped: "bg-slate-200 text-slate-700",
  running: "bg-sky-100 text-sky-800",
  failed: "bg-rose-100 text-rose-800",
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] ?? "bg-slate-100 text-slate-700"}`}>
      {status}
    </span>
  );
}
