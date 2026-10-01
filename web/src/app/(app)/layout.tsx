import { ReactNode } from "react";
import AppShell from "@/components/app-shell";
import { Spinner } from "@/components/ui";
import { SessionProvider } from "@/lib/session";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <SessionProvider fallback={<Spinner label="Opening the till…" />}>
      <AppShell>{children}</AppShell>
    </SessionProvider>
  );
}
