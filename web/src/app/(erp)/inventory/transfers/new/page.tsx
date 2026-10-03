"use client";

import { PageHeader } from "@/components/erp/common";
import { StockDocForm } from "@/components/erp/stock-doc-form";

export default function NewTransferPage() {
  return (
    <>
      <PageHeader title="New transfer" description="Move stock from one warehouse to another." />
      <StockDocForm kind="transfer" />
    </>
  );
}
