"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams } from "next/navigation";
import { PartnerDetail } from "@/components/erp/partner-detail";
import { Skeleton } from "@/components/ui/skeleton";
import { get } from "@/lib/api";
import type { SupplierDetail } from "@/lib/types";

export default function SupplierPage() {
  const { id } = useParams<{ id: string }>();
  const { data } = useQuery({ queryKey: ["/api/suppliers", id], queryFn: () => get<SupplierDetail>(`/api/suppliers/${id}`) });
  return data ? <PartnerDetail kind="supplier" partner={data} /> : <Skeleton className="h-[500px]" />;
}
