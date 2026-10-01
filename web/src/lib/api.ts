export const API_URL = process.env.NEXT_PUBLIC_POS_API_URL ?? "http://localhost:8000";

export type Register = { id: number; code: string; name: string };
export type Location = { id: number; code: string; name: string; city: string; registers: Register[] };
export type Product = {
  id: number;
  sku: string;
  name: string;
  barcode: string | null;
  brand: string;
  category: string;
  price: number;
  on_hand: number;
};
export type Customer = {
  id: number;
  code: string;
  name: string;
  phone: string;
  email: string | null;
  group: string | null;
  discount_rate: number;
};
export type PushStatus = "pending" | "sent" | "failed";
export type Order = {
  id: number;
  number: string;
  external_id: string;
  created_at: string;
  location: string;
  register: string | null;
  customer: string | null;
  subtotal: number;
  discount: number;
  total: number;
  paid: number;
  change: number;
  push_status: PushStatus;
  push_attempts: number;
  next_push_at: string | null;
  last_push_error: string | null;
  erp_number: string | null;
  lines?: { product_id: number; sku: string; name: string; qty: number; unit_price: number; line_total: number }[];
  payments?: { method: string; amount: number }[];
  push_log?: { attempt: number; ok: boolean; status_code: number | null; error: string | null; at: string }[];
};
export type MirrorSummary = {
  rows?: number;
  inserted?: number;
  updated?: number;
  removed?: number;
  errors?: number;
  skipped?: boolean;
  error?: string;
};
export type SyncRun = {
  id: number;
  status: "running" | "ok" | "partial" | "failed";
  started_at: string;
  finished_at: string | null;
  summary: Record<string, MirrorSummary>;
};
export type SyncEvent = {
  id: number;
  table: string;
  action: string;
  erp_public_id: string | null;
  message: string | null;
  at: string;
};
export type SyncState = { key: string; last_status: string; last_synced_at: string | null; rows: number };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = await res.json();
      message = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(res.status, message);
  }
  return res.json() as Promise<T>;
}

const rupiahFormat = new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 });
export const rupiah = (n: number) => rupiahFormat.format(n);

// The API sends naive UTC timestamps.
export const localTime = (iso: string) =>
  new Date(iso.endsWith("Z") ? iso : `${iso}Z`).toLocaleString("id-ID", { dateStyle: "short", timeStyle: "medium" });
