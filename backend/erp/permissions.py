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
}

_ALL = set(PERMISSIONS)

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
}


def permissions_for(role: str) -> set[str]:
    return set(ROLES.get(role, {"permissions": set()})["permissions"])
