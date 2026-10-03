// Shapes returned by the ERP API (see backend/erp/api).

export type Ref = { id: number; name: string };
export type CodeRef = { id: number; code: string; name: string };
export type ProductRef = { id: number; sku: string; name: string; unit: string };
export type UserRef = { id: number; name: string } | null;

export type Activity = {
  id: number;
  at: string;
  user: UserRef;
  entity_type: string;
  entity_id: number;
  action: string;
  message: string;
};

export type ProductRow = {
  id: number;
  sku: string;
  name: string;
  brand: string | null;
  barcode: string | null;
  unit: string;
  category: Ref | null;
  sale_price: number;
  avg_cost: number;
  reorder_point: number;
  active: boolean;
  on_hand: number;
  reserved: number;
  available: number;
  incoming: number;
  low_stock: boolean;
};

export type StockByWarehouse = {
  warehouse: CodeRef;
  on_hand: number;
  reserved: number;
  available: number;
  incoming: number;
};

export type StockMove = {
  id: number;
  at: string;
  warehouse: CodeRef;
  product?: ProductRef;
  qty: number;
  unit_cost: number;
  kind: string;
  ref_type: string | null;
  ref_id: number | null;
  ref_number: string | null;
  user: UserRef;
};

export type ProductDetail = ProductRow & {
  description: string | null;
  stock_value: number;
  warehouses: StockByWarehouse[];
  recent_moves: StockMove[];
  activity: Activity[];
};

export type Warehouse = CodeRef & { city: string; address: string | null; active: boolean; units: number; stock_value: number };
export type Category = { id: number; name: string; products: number };
export type CustomerGroup = { id: number; code: string; name: string; discount_pct: number; customers: number };

type DocSummary = { id: number; number: string; status: string; total: number };
type InvoiceSummary = DocSummary & { issue_date: string; due_date: string; balance: number };

export type Customer = {
  id: number;
  code: string;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  city: string | null;
  active: boolean;
  credit_limit: number;
  payment_terms_days: number;
  group: { id: number; name: string; discount_pct: number } | null;
  balance: number;
  overdue: number;
  /** Earned and spent at the POS tills. */
  loyalty_points: number;
};
export type CustomerDetail = Customer & {
  credit_used: number;
  lifetime_revenue: number;
  recent_orders: (DocSummary & { order_date: string })[];
  recent_invoices: InvoiceSummary[];
  activity: Activity[];
};

export type Supplier = Omit<Customer, "group" | "credit_limit" | "loyalty_points">;
export type SupplierDetail = Supplier & {
  lifetime_spend: number;
  recent_orders: (DocSummary & { order_date: string })[];
  recent_bills: InvoiceSummary[];
  activity: Activity[];
};

export type OrderLine = {
  id: number;
  product: ProductRef;
  qty: number;
  line_total: number;
};

export type SalesOrder = {
  id: number;
  number: string;
  status: string;
  invoice_status: string;
  customer: CodeRef;
  warehouse: CodeRef;
  order_date: string;
  customer_ref: string | null;
  source: "manual" | "api";
  external_id: string | null;
  gross: number;
  discount: number;
  subtotal: number;
  tax_rate: number;
  tax: number;
  total: number;
  delivered_pct: number;
};
export type Shipment = { id: number; number: string; units: number; created_by: UserRef; lines: { product: ProductRef; qty: number }[] };
export type SalesOrderDetail = SalesOrder & {
  note: string | null;
  created_by: UserRef;
  created_at: string;
  lines: (OrderLine & {
    unit_price: number;
    discount_pct: number;
    qty_delivered: number;
    qty_invoiced: number;
    qty_returned: number;
    stock: { on_hand: number; available: number } | null;
  })[];
  deliveries: (Shipment & { delivery_date: string })[];
  invoices: InvoiceSummary[];
  returns: SalesReturn[];
  points_earned: number;
  activity: Activity[];
};
export type SalesReturn = {
  id: number;
  number: string;
  return_date: string;
  reason: string | null;
  subtotal: number;
  tax: number;
  total: number;
  units: number;
  points_reversed: number;
  refunds: { method: string; amount: number; reference: string | null }[];
  lines: { product: ProductRef; qty: number; line_total: number }[];
};

export type PromotionKind = "percent" | "price" | "buy_get" | "voucher";
export type Promotion = {
  id: number;
  name: string;
  kind: PromotionKind;
  value: number;
  buy_qty: number;
  get_qty: number;
  code: string | null;
  min_spend: number;
  starts_on: string | null;
  ends_on: string | null;
  active: boolean;
  status: "running" | "scheduled" | "ended" | "inactive";
  product: ProductRef | null;
  category: { id: number; name: string } | null;
  warehouse: CodeRef | null;
};

export type PurchaseOrder = {
  id: number;
  number: string;
  status: string;
  billing_status: string;
  supplier: CodeRef;
  warehouse: CodeRef;
  order_date: string;
  expected_date: string | null;
  supplier_ref: string | null;
  subtotal: number;
  tax_rate: number;
  tax: number;
  total: number;
  received_pct: number;
};
export type PurchaseOrderDetail = PurchaseOrder & {
  note: string | null;
  created_by: UserRef;
  created_at: string;
  lines: (OrderLine & { unit_cost: number; qty_received: number; qty_billed: number })[];
  receipts: (Shipment & { receipt_date: string })[];
  bills: InvoiceSummary[];
  activity: Activity[];
};

export type Payment = {
  id: number;
  number: string;
  payment_date: string;
  amount: number;
  method: string;
  reference: string | null;
  created_by: UserRef;
};

export type Invoice = {
  id: number;
  number: string;
  kind: "customer" | "supplier";
  status: string;
  partner: CodeRef;
  issue_date: string;
  due_date: string;
  days_overdue: number;
  partner_ref: string | null;
  subtotal: number;
  tax_rate: number;
  tax: number;
  total: number;
  amount_paid: number;
  balance: number;
  source: { type: "sales_order" | "purchase_order"; id: number; number: string } | null;
};
export type InvoiceDetail = Invoice & {
  partner_details: { address: string | null; city: string | null; phone: string | null; email: string | null; payment_terms_days: number };
  created_by: UserRef;
  created_at: string;
  lines: { id: number; product: ProductRef; qty: number; unit_price: number; discount_pct: number; line_total: number }[];
  payments: Payment[];
  activity: Activity[];
};

export type Transfer = {
  id: number;
  number: string;
  status: string;
  transfer_date: string;
  from_warehouse: CodeRef;
  to_warehouse: CodeRef;
  note: string | null;
  units: number;
  created_by: UserRef;
  lines?: { id: number; product: ProductRef; qty: number }[];
  activity?: Activity[];
};

export type Adjustment = {
  id: number;
  number: string;
  status: string;
  adjustment_date: string;
  warehouse: CodeRef;
  reason: string;
  products: number;
  created_by: UserRef;
  lines?: { id: number; product: ProductRef; counted_qty: number; system_qty: number; difference: number; value: number }[];
  activity?: Activity[];
};

export type Dashboard = {
  revenue_30d: number;
  revenue_prev_30d: number;
  gross_profit_30d: number;
  receivables: { amount: number; count: number; overdue: number; overdue_count: number };
  payables: { amount: number; count: number; overdue: number; overdue_count: number };
  stock_value: number;
  orders_to_deliver: number;
  orders_to_receive: number;
  low_stock: { id: number; sku: string; name: string; on_hand: number; reorder_point: number }[];
  monthly: { month: string; revenue: number; cogs: number; purchases: number; gross_profit: number }[];
  top_products: { id: number; sku: string; name: string; qty: number; revenue: number }[];
};
