import { CheckCircle2, CircleAlert, Clock } from "lucide-react";
import { Order } from "@/lib/api";

/** Whether head office (the ERP) has the sale yet, in words a cashier understands. */
export default function SyncStatus({ order, long }: { order: Order; long?: boolean }) {
  if (order.push_status === "sent") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-emerald-700" title={`Head office number ${order.erp_number}`}>
        <CheckCircle2 className="h-4 w-4" /> {long ? `Sent to head office (${order.erp_number})` : "Sent"}
      </span>
    );
  }
  if (order.push_status === "pending") {
    return (
      <span className="inline-flex items-center gap-1 text-xs text-amber-700" title="Saved here; it will be sent to head office automatically.">
        <Clock className="h-4 w-4" /> {long ? "Saved, waiting to send to head office" : "Waiting"}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-rose-700" title={order.last_push_error ?? ""}>
      <CircleAlert className="h-4 w-4" /> {long ? "Head office did not accept it: an admin needs to check" : "Needs check"}
    </span>
  );
}
