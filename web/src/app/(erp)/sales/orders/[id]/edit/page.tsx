"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { PageHeader } from "@/components/erp/common";
import { OrderForm } from "@/components/erp/order-form";
import { Skeleton } from "@/components/ui/skeleton";
import { get } from "@/lib/api";
import type { SalesOrderDetail } from "@/lib/types";

export default function EditSalesOrderPage() {
  const { id } = useParams<{ id: string }>();
  const { data } = useQuery({ queryKey: ["/api/sales-orders", id], queryFn: () => get<SalesOrderDetail>(`/api/sales-orders/${id}`) });
  if (!data) return <Skeleton className="h-96" />;
  return (
    <>
      <PageHeader title={`Edit ${data.number}`} description="Only drafts can be edited." />
      <OrderForm kind="sales" order={data} />
    </>
  );
}
