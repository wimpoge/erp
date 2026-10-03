"use client";

import { PageHeader } from "@/components/erp/common";
import { OrderForm } from "@/components/erp/order-form";

export default function NewSalesOrderPage() {
  return (
    <>
      <PageHeader title="New sales order" description="Prices come from the product list; the customer's group discount is applied." />
      <OrderForm kind="sales" />
    </>
  );
}
