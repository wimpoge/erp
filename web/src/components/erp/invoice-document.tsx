import { dateLabel, money, qty } from "@/lib/format";
import type { Company } from "@/lib/hooks";
import type { InvoiceDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

const METHOD: Record<string, string> = { bank_transfer: "Bank transfer", cash: "Cash", card: "Card", qris: "QRIS" };

/**
 * The printed invoice / supplier bill: an A4 business document, not a copy of the screen.
 * Hidden on screen; the only thing on the page when printing.
 */
export function InvoiceDocument({ invoice: inv, company }: { invoice: InvoiceDetail; company?: Company }) {
  const customer = inv.kind === "customer";
  const p = inv.partner_details;
  const paid = inv.balance === 0 && inv.status !== "cancelled";
  const discounted = inv.lines.some((l) => l.discount_pct > 0);

  return (
    <article className="hidden text-[11px] leading-relaxed text-neutral-900 [print-color-adjust:exact] print:block">
      {/* Letterhead */}
      <header className="flex items-start justify-between gap-8 border-b-2 border-neutral-900 pb-5">
        <div className="flex gap-3">
          <div className="flex size-11 shrink-0 items-center justify-center rounded-md bg-neutral-900 text-lg font-bold text-white">
            {company?.company_name?.[0] ?? "N"}
          </div>
          <div>
            <p className="text-base font-semibold">{company?.company_name}</p>
            <p className="text-neutral-600">{company?.company_address}</p>
            <p className="text-neutral-600">
              {[company?.company_phone, company?.company_email].filter(Boolean).join(" · ")}
            </p>
            {company?.company_tax_id && <p className="text-neutral-600">NPWP {company.company_tax_id}</p>}
          </div>
        </div>
        <div className="text-right">
          <p className="text-3xl font-bold tracking-tight uppercase">{customer ? "Invoice" : "Supplier bill"}</p>
          <p className="mt-1 font-mono text-xs">{inv.number}</p>
          <Stamp invoice={inv} />
        </div>
      </header>

      {/* Parties and dates */}
      <section className="mt-6 grid grid-cols-[1.2fr_1fr] gap-10">
        <div>
          <Label>{customer ? "Bill to" : "From supplier"}</Label>
          <p className="text-sm font-semibold">{inv.partner.name}</p>
          <p className="text-neutral-500">{customer ? "Customer" : "Supplier"} no. {inv.partner.code}</p>
          {p.address && <p>{p.address}</p>}
          {p.city && <p>{p.city}</p>}
          {(p.phone || p.email) && <p className="text-neutral-600">{[p.phone, p.email].filter(Boolean).join(" · ")}</p>}
        </div>
        <dl className="grid grid-cols-[auto_1fr] content-start gap-x-6 gap-y-1">
          <Meta label={customer ? "Invoice date" : "Bill date"} value={dateLabel(inv.issue_date)} />
          <Meta label="Due date" value={dateLabel(inv.due_date)} strong />
          <Meta label="Payment terms" value={`${p.payment_terms_days} days`} />
          {inv.source && <Meta label={customer ? "Sales order" : "Purchase order"} value={inv.source.number} mono />}
          {inv.partner_ref && <Meta label={customer ? "Your reference" : "Supplier invoice no."} value={inv.partner_ref} />}
        </dl>
      </section>

      {/* Lines */}
      <table className="mt-7 w-full border-collapse">
        <thead>
          <tr className="bg-neutral-100 text-left text-[10px] tracking-wide text-neutral-600 uppercase">
            <th className="w-8 px-2 py-2 font-medium">#</th>
            <th className="px-2 py-2 font-medium">Description</th>
            <th className="px-2 py-2 text-right font-medium">Qty</th>
            <th className="px-2 py-2 text-right font-medium">Unit price</th>
            {discounted && <th className="px-2 py-2 text-right font-medium">Disc.</th>}
            <th className="px-2 py-2 text-right font-medium">Amount</th>
          </tr>
        </thead>
        <tbody>
          {inv.lines.map((l, i) => (
            <tr key={l.id} className="border-b border-neutral-200 align-top">
              <td className="px-2 py-2.5 text-neutral-500 tabular-nums">{i + 1}</td>
              <td className="px-2 py-2.5">
                <p className="font-medium">{l.product.name}</p>
                <p className="font-mono text-[10px] text-neutral-500">{l.product.sku}</p>
              </td>
              <td className="px-2 py-2.5 text-right tabular-nums">
                {qty(l.qty)} {l.product.unit}
              </td>
              <td className="px-2 py-2.5 text-right tabular-nums">{money(l.unit_price)}</td>
              {discounted && <td className="px-2 py-2.5 text-right tabular-nums">{l.discount_pct ? `${l.discount_pct}%` : "—"}</td>}
              <td className="px-2 py-2.5 text-right font-medium tabular-nums">{money(l.line_total)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* Payment instructions and totals */}
      <section className="mt-6 grid grid-cols-[1fr_17rem] items-start gap-10">
        <div className="space-y-4">
          {customer && !paid && company?.bank_account && (
            <div className="rounded-md border border-neutral-300 p-3">
              <Label>How to pay</Label>
              <p>
                Transfer <span className="font-semibold">{money(inv.balance)}</span> by {dateLabel(inv.due_date)} to:
              </p>
              <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-4">
                <Meta label="Bank" value={company.bank_name} />
                <Meta label="Account no." value={company.bank_account} mono />
                <Meta label="Account name" value={company.bank_holder} />
                <Meta label="Reference" value={inv.number} mono />
              </dl>
            </div>
          )}
          {inv.payments.length > 0 && (
            <div>
              <Label>Payments {customer ? "received" : "made"}</Label>
              <table className="w-full">
                <tbody>
                  {inv.payments.map((pay) => (
                    <tr key={pay.id} className="border-b border-neutral-100">
                      <td className="py-1">{dateLabel(pay.payment_date)}</td>
                      <td className="py-1 text-neutral-600">{METHOD[pay.method] ?? pay.method}</td>
                      <td className="py-1 font-mono text-[10px] text-neutral-500">{pay.number}</td>
                      <td className="py-1 text-right tabular-nums">{money(pay.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <dl className="text-xs">
          <Total label="Subtotal" value={money(inv.subtotal)} />
          <Total label={`VAT ${inv.tax_rate}%`} value={money(inv.tax)} />
          <div className="mt-1 flex justify-between rounded-md bg-neutral-900 px-3 py-2 text-sm font-semibold text-white">
            <dt>Total</dt>
            <dd className="tabular-nums">{money(inv.total)}</dd>
          </div>
          {inv.amount_paid > 0 && <Total label="Paid" value={`−${money(inv.amount_paid)}`} />}
          <div className="mt-1 flex justify-between border-t border-neutral-300 px-3 pt-2 text-sm font-semibold">
            <dt>Balance due</dt>
            <dd className="tabular-nums">{money(inv.balance)}</dd>
          </div>
        </dl>
      </section>

      <footer className="mt-12 border-t border-neutral-200 pt-3 text-[10px] text-neutral-500">
        <p className="text-neutral-700">
          {customer ? "Thank you for your business." : "Recorded against the purchase order above."} Questions about this
          document: {company?.company_email || company?.company_phone}.
        </p>
        <p className="mt-0.5">Amounts in Indonesian rupiah. Generated by Nusantara ERP.</p>
      </footer>
    </article>
  );
}

function Stamp({ invoice }: { invoice: InvoiceDetail }) {
  const s = invoice.status;
  const [label, tone] =
    s === "cancelled" ? ["Cancelled", "border-neutral-400 text-neutral-500"]
    : invoice.balance === 0 ? ["Paid", "border-emerald-600 text-emerald-700"]
    : s === "overdue" ? [`Overdue · ${invoice.days_overdue} days`, "border-red-600 text-red-700"]
    : [`Due ${dateLabel(invoice.due_date)}`, "border-neutral-900 text-neutral-900"];
  return (
    <span className={cn("mt-2 inline-block rounded border-2 px-2 py-0.5 text-[10px] font-bold tracking-wider uppercase", tone)}>
      {label}
    </span>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <p className="mb-1 text-[10px] font-medium tracking-wider text-neutral-500 uppercase">{children}</p>;
}

function Meta({ label, value, strong, mono }: { label: string; value: React.ReactNode; strong?: boolean; mono?: boolean }) {
  return (
    <>
      <dt className="text-neutral-500">{label}</dt>
      <dd className={cn(strong && "font-semibold", mono && "font-mono text-[10px]")}>{value || "—"}</dd>
    </>
  );
}

function Total({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between px-3 py-1">
      <dt className="text-neutral-600">{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}
