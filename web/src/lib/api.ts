export type Register = { id: number; code: string; name: string };
export type Location = { id: number; code: string; name: string; city: string; registers: Register[] };
export type User = {
  id: number;
  username: string;
  full_name: string;
  role: "cashier" | "admin";
  active: boolean;
  location: Location | null;
  last_login_at: string | null;
  locked: boolean;
};
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
  location_name: string;
  register: string | null;
  customer: string | null;
  cashier: string | null;
  subtotal: number;
  discount: number;
  total: number;
  paid: number;
  change: number;
  items: number;
  push_status: PushStatus;
  push_attempts: number;
  next_push_at: string | null;
  last_push_error: string | null;
  erp_number: string | null;
  lines?: { product_id: number; sku: string; name: string; qty: number; unit_price: number; line_total: number }[];
  payments?: { method: string; amount: number }[];
  push_log?: { attempt: number; ok: boolean; status_code: number | null; error: string | null; at: string }[];
};
export type SalesSummary = { count: number; revenue: number; by_method: Record<string, number> };
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
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** Calls the POS API through this app's /api proxy, with the session cookie. */
export async function api<T>(path: string, init?: RequestInit & { json?: unknown }): Promise<T> {
  const { json, ...rest } = init ?? {};
  let res: Response;
  try {
    res = await fetch(path, {
      ...rest,
      body: json === undefined ? rest.body : JSON.stringify(json),
      headers: { "content-type": "application/json", ...rest.headers },
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check the connection and try again.");
  }
  if (res.status === 401 && !path.startsWith("/api/auth/")) {
    // Session ended (expired or logged out elsewhere): back to the login page. This runs
    // outside React, so a full page load (which also drops any stale in-memory state).
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
    throw new ApiError(401, "Your session has ended. Please log in again.");
  }
  if (!res.ok) {
    let message = res.status >= 500 ? "Something went wrong on the server. Please try again." : res.statusText;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d: { msg: string }) => d.msg).join(", ");
    } catch {}
    throw new ApiError(res.status, message);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const errorMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));

const rupiahFormat = new Intl.NumberFormat("id-ID", { style: "currency", currency: "IDR", maximumFractionDigits: 0 });
export const rupiah = (n: number) => rupiahFormat.format(n);

// The API sends naive UTC timestamps.
export const parseTime = (iso: string) => new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
export const timeOnly = (iso: string) => parseTime(iso).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
export const dateTime = (iso: string) =>
  parseTime(iso).toLocaleString("id-ID", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function startOfToday(): string {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}
