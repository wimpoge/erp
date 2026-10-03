"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { get } from "./api";
import type { Warehouse } from "./types";

export function useWarehouses() {
  return useQuery({ queryKey: ["warehouses"], queryFn: () => get<Warehouse[]>("/api/warehouses"), staleTime: 5 * 60_000 });
}

export type Company = {
  company_name: string;
  company_address: string;
  company_phone: string;
  company_email: string;
  company_tax_id: string;
  bank_name: string;
  bank_account: string;
  bank_holder: string;
  tax_rate: number;
  currency: string;
};

export function useCompany() {
  return useQuery({ queryKey: ["company"], queryFn: () => get<Company>("/api/settings/company"), staleTime: 5 * 60_000 });
}

/**
 * A button-sized server action: runs, refreshes every list and detail on screen, and says
 * what happened. Errors are toasted by the global mutation cache.
 */
export function useAction<TArgs = void, TResult = unknown>(
  fn: (args: TArgs) => Promise<TResult>,
  success?: string | ((result: TResult) => string),
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (result) => {
      await client.invalidateQueries();
      if (success) toast.success(typeof success === "function" ? success(result) : success);
    },
  });
}
