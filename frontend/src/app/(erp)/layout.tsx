"use client";

import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { AppSidebar } from "@/components/erp/app-sidebar";
import { findNav } from "@/components/erp/nav";
import { Separator } from "@/components/ui/separator";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { Spinner } from "@/components/ui/spinner";
import { AuthProvider } from "@/lib/auth";

export default function ErpLayout({ children }: { children: ReactNode }) {
  return (
    <AuthProvider
      fallback={
        <div className="flex h-svh items-center justify-center gap-2 text-sm text-muted-foreground">
          <Spinner /> Loading…
        </div>
      }
    >
      <SidebarProvider>
        <AppSidebar />
        <SidebarInset className="h-svh overflow-hidden">
          <Header />
          <div data-slot="page" className="flex min-h-0 flex-1 flex-col gap-6 overflow-y-auto p-4 md:p-6">
            {children}
          </div>
        </SidebarInset>
      </SidebarProvider>
    </AuthProvider>
  );
}

function Header() {
  const nav = findNav(usePathname());
  return (
    <header className="flex h-14 shrink-0 print:hidden items-center gap-2 border-b bg-background/95 px-4 backdrop-blur">
      <SidebarTrigger className="-ml-1" />
      <Separator orientation="vertical" className="mr-2 data-vertical:h-4" />
      {nav && (
        <p className="text-sm text-muted-foreground">
          {nav.group.label} <span className="mx-1">/</span>
          <span className="text-foreground">{nav.item.title}</span>
        </p>
      )}
    </header>
  );
}
