"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { createContext, ReactNode, useContext, useEffect } from "react";
import { api } from "./api";

export type Me = {
  id: number;
  username: string;
  email: string;
  full_name: string;
  role: string;
  role_label: string;
  permissions: string[];
  company: { company_name: string; currency: string };
};

const AuthContext = createContext<Me | null>(null);

export function useMe(): Me {
  const me = useContext(AuthContext);
  if (!me) throw new Error("useMe outside AuthProvider");
  return me;
}

/** `can("sales.write")`: hide what the role may not do (the API enforces it regardless). */
export function useCan() {
  const me = useMe();
  return (permission: string) => me.permissions.includes(permission);
}

export function AuthProvider({ children, fallback }: { children: ReactNode; fallback: ReactNode }) {
  const router = useRouter();
  const { data, isError } = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/auth/me"), retry: false });

  useEffect(() => {
    if (isError) router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
  }, [isError, router]);

  if (!data) return <>{fallback}</>;
  return <AuthContext.Provider value={data}>{children}</AuthContext.Provider>;
}
