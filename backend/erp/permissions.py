"""Roles map to permissions; endpoints ask for permissions, never for roles."""

PERMISSIONS = {
    "catalog.read": "See products, warehouses and stock",
    "catalog.write": "Create and edit products, categories and warehouses",
    "inventory.write": "Transfer stock and post stock counts",
    "purchasing.read": "See suppliers and purchase orders",
    "purchasing.write": "Create suppliers and purchase orders",
    "purchasing.receive": "Receive goods into a warehouse",
    "sales.read": "See customers and sales orders",
    "sales.write": "Create customers and sales orders",
    "sales.deliver": "Ship goods from a warehouse",
    "finance.read": "See invoices, bills and payments",
    "finance.write": "Create invoices and bills, register payments",
    "reports.read": "See the dashboard and reports",
    "settings.manage": "Manage users, API clients and company settings",
    "pos.sell": "Sell at the POS tills (logs in at the POS, not here)",
    "pos.approve": "Approve big discounts, voids, refunds and large cash-outs at a POS till",
}

# Office roles work in the ERP; selling at a till is the cashier's job alone.
_ALL = set(PERMISSIONS) - {"pos.sell"}

ROLES: dict[str, dict] = {
    "admin": {"label": "Administrator", "permissions": _ALL},
    "manager": {"label": "Manager", "permissions": _ALL - {"settings.manage"}},
    "sales": {
        "label": "Sales",
        "permissions": {"catalog.read", "sales.read", "sales.write", "finance.read", "reports.read"},
    },
    "purchasing": {
        "label": "Purchasing",
        "permissions": {"catalog.read", "purchasing.read", "purchasing.write", "finance.read", "reports.read"},
    },
    "warehouse": {
        "label": "Warehouse",
        "permissions": {"catalog.read", "inventory.write", "sales.read", "sales.deliver", "purchasing.read",
                        "purchasing.receive"},
    },
    "accountant": {
        "label": "Accountant",
        "permissions": {"catalog.read", "sales.read", "purchasing.read", "finance.read", "finance.write",
                        "reports.read"},
    },
    "cashier": {"label": "Cashier", "permissions": {"pos.sell"}},
}


def is_pos_only(role: str) -> bool:
    """A till account: it has no ERP screens, so it logs in at the POS instead."""
    return permissions_for(role) == {"pos.sell"}


def permissions_for(role: str) -> set[str]:
    return set(ROLES.get(role, {"permissions": set()})["permissions"])
