"use client";

import { PageHeader } from "@/components/erp/common";
import { StockDocForm } from "@/components/erp/stock-doc-form";

export default function NewAdjustmentPage() {
  return (
    <>
      <PageHeader title="New stock count" description="Enter what is actually on the shelf. Only the products you list are changed." />
      <StockDocForm kind="count" />
    </>
  );
}
