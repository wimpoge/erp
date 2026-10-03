import {
  ArrowLeftRight,
  BarChart3,
  Boxes,
  ClipboardList,
  FileText,
  Handshake,
  History,
  KeyRound,
  LayoutDashboard,
  Package,
  ReceiptText,
  Tag,
  Settings2,
  ShoppingCart,
  Truck,
  Users,
  Wallet,
  Warehouse,
  type LucideIcon,
} from "lucide-react";

export type NavItem = { title: string; href: string; icon: LucideIcon; permission: string };
export type NavGroup = { label: string; items: NavItem[] };

export const NAV: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { title: "Dashboard", href: "/", icon: LayoutDashboard, permission: "reports.read" },
      { title: "Reports", href: "/reports", icon: BarChart3, permission: "reports.read" },
    ],
  },
  {
    label: "Sales",
    items: [
      { title: "Sales orders", href: "/sales/orders", icon: ShoppingCart, permission: "sales.read" },
      { title: "Customers", href: "/sales/customers", icon: Users, permission: "sales.read" },
      { title: "Promotions", href: "/sales/promotions", icon: Tag, permission: "sales.read" },
    ],
  },
  {
    label: "Purchasing",
    items: [
      { title: "Purchase orders", href: "/purchasing/orders", icon: Truck, permission: "purchasing.read" },
      { title: "Suppliers", href: "/purchasing/suppliers", icon: Handshake, permission: "purchasing.read" },
    ],
  },
  {
    label: "Inventory",
    items: [
      { title: "Products", href: "/inventory/products", icon: Package, permission: "catalog.read" },
      { title: "Stock levels", href: "/inventory/stock", icon: Boxes, permission: "catalog.read" },
      { title: "Transfers", href: "/inventory/transfers", icon: ArrowLeftRight, permission: "catalog.read" },
      { title: "Stock counts", href: "/inventory/adjustments", icon: ClipboardList, permission: "catalog.read" },
      { title: "Movements", href: "/inventory/moves", icon: History, permission: "catalog.read" },
      { title: "Warehouses", href: "/inventory/warehouses", icon: Warehouse, permission: "catalog.read" },
    ],
  },
  {
    label: "Finance",
    items: [
      { title: "Customer invoices", href: "/finance/invoices", icon: FileText, permission: "finance.read" },
      { title: "Supplier bills", href: "/finance/bills", icon: ReceiptText, permission: "finance.read" },
      { title: "Payments", href: "/finance/payments", icon: Wallet, permission: "finance.read" },
    ],
  },
  {
    label: "Settings",
    items: [
      { title: "Users & roles", href: "/settings/users", icon: Users, permission: "settings.manage" },
      { title: "API clients", href: "/settings/api-clients", icon: KeyRound, permission: "settings.manage" },
      { title: "Company", href: "/settings/company", icon: Settings2, permission: "settings.manage" },
    ],
  },
];

export function findNav(pathname: string): { group: NavGroup; item: NavItem } | null {
  let best: { group: NavGroup; item: NavItem } | null = null;
  for (const group of NAV)
    for (const item of group.items) {
      const match = item.href === "/" ? pathname === "/" : pathname === item.href || pathname.startsWith(item.href + "/");
      if (match && (!best || item.href.length > best.item.href.length)) best = { group, item };
    }
  return best;
}
