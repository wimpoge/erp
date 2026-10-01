import { dateTime, Order, rupiah } from "@/lib/api";

/** 80 mm thermal-style receipt. Hidden on screen, the only thing printed. */
export default function PrintableReceipt({ order }: { order: Order | null }) {
  if (!order) return null;
  return (
    <div className="hidden w-[72mm] font-mono text-[11px] leading-snug text-black print:block">
      <p className="text-center text-sm font-bold">KIOS GAWAI</p>
      <p className="text-center">{order.location_name}</p>
      <p className="mt-2">{order.number}</p>
      <p>
        {dateTime(order.created_at)} · {order.register ?? ""}
      </p>
      <p>Cashier: {order.cashier ?? "-"}</p>
      {order.customer && <p>Customer: {order.customer}</p>}
      <hr className="my-1 border-dashed border-black" />
      {order.lines?.map((l) => (
        <div key={l.product_id}>
          <p>{l.name}</p>
          <p className="flex justify-between">
            <span>
              {l.qty} x {rupiah(l.unit_price)}
            </span>
            <span>{rupiah(l.line_total)}</span>
          </p>
        </div>
      ))}
      <hr className="my-1 border-dashed border-black" />
      <ReceiptRow label="Subtotal" value={rupiah(order.subtotal)} />
      {order.discount > 0 && <ReceiptRow label="Member discount" value={`-${rupiah(order.discount)}`} />}
      <ReceiptRow label="TOTAL" value={rupiah(order.total)} bold />
      {order.payments?.map((p, i) => (
        <ReceiptRow key={i} label={p.method.toUpperCase()} value={rupiah(p.amount)} />
      ))}
      <ReceiptRow label="Change" value={rupiah(order.change)} />
      <p className="mt-3 text-center">Thank you for shopping!</p>
    </div>
  );
}

function ReceiptRow({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <p className={`flex justify-between ${bold ? "font-bold" : ""}`}>
      <span>{label}</span>
      <span>{value}</span>
    </p>
  );
}
