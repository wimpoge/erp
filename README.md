# ERP

Live demo: https://erp-otw7.vercel.app

## Features

- **Dashboard**: sales, profit, receivables, payables, stock value and low-stock alerts
- **Sales**: customers, discount groups, credit limits, sales orders, partial deliveries
- **Purchasing**: suppliers, purchase orders, partial goods receipts, supplier bills
- **Inventory**: stock per warehouse, transfers, stock counts, full movement history, average cost
- **Finance**: invoices, bills, partial payments, overdue tracking, printable A4 invoices
- **Reports**: monthly sales and profit, best sellers, top customers, stock value, aging
- **Users & roles**: six roles (admin, manager, sales, purchasing, warehouse, finance), each with its own access
- **Integration API**: lets a POS or web shop read products and stock and send in orders

## Tech stack

- **Frontend**: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, Recharts
- **Backend**: Python, FastAPI, SQLAlchemy, Alembic, pytest
- **Database**: PostgreSQL (Neon)
- **Hosting**: Vercel
