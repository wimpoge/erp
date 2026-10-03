"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { PartnerDetail } from "@/components/erp/partner-detail";
import { Skeleton } from "@/components/ui/skeleton";
import { get } from "@/lib/api";
import type { CustomerDetail } from "@/lib/types";

export default function CustomerPage() {
  const { id } = useParams<{ id: string }>();
  const { data } = useQuery({ queryKey: ["/api/customers", id], queryFn: () => get<CustomerDetail>(`/api/customers/${id}`) });
  return data ? <PartnerDetail kind="customer" partner={data} /> : <Skeleton className="h-[500px]" />;
}
