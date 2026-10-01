"use client";

import { ShieldAlert } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { EmptyState } from "@/components/ui";
import { useSession } from "@/lib/session";

const tabs = [
  { href: "/backoffice", label: "Sales queue" },
  { href: "/backoffice/sync", label: "Head office sync" },
  { href: "/backoffice/staff", label: "Staff" },
];

export default function BackofficeLayout({ children }: { children: ReactNode }) {
  const { user } = useSession();
  const pathname = usePathname();

  if (user.role !== "admin") {
    return (
      <EmptyState icon={<ShieldAlert className="h-12 w-12" />} title="Admins only">
        Ask an admin if you need something changed here.
      </EmptyState>
    );
  }
  return (
    <div className="mx-auto max-w-6xl space-y-5 p-4 sm:p-6">
      <div>
        <h1 className="text-xl font-semibold">Back office</h1>
        <nav className="mt-3 flex gap-1 border-b border-slate-200">
          {tabs.map((t) => (
            <Link
              key={t.href}
              href={t.href}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
                pathname === t.href ? "border-sky-500 text-slate-900" : "border-transparent text-slate-500 hover:text-slate-800"
              }`}
            >
              {t.label}
            </Link>
          ))}
        </nav>
      </div>
      {children}
    </div>
  );
}
