/** Where a record lives in the UI, for activity feeds and cross-links. */
export function entityHref(type: string, id: number): string | null {
  switch (type) {
    case "sales_order":
      return `/sales/orders/${id}`;
    case "purchase_order":
      return `/purchasing/orders/${id}`;
    case "invoice":
      return `/finance/invoices/${id}`;
    case "transfer":
      return `/inventory/transfers/${id}`;
    case "adjustment":
      return `/inventory/adjustments/${id}`;
    case "customer":
      return `/sales/customers/${id}`;
    case "supplier":
      return `/purchasing/suppliers/${id}`;
    case "product":
      return `/inventory/products/${id}`;
    default:
      return null;
  }
}

export const refHref = (refType: string | null, refId: number | null): string | null => {
  if (!refType || !refId) return null;
  // Stock moves point at receipts/deliveries; those live on their order's page.
  return entityHref(refType, refId);
};
