"use client";

import { PageHeader } from "@/components/erp/common";
import { OrderForm } from "@/components/erp/order-form";

export default function NewPurchaseOrderPage() {
  return (
    <>
      <PageHeader title="New purchase order" description="Costs default to each product's current average cost; use the supplier's quote." />
      <OrderForm kind="purchase" />
    </>
  );
}
