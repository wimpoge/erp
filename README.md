# Nusantara ERP

A web ERP for a multi-warehouse retailer of phones and accessories: **inventory, purchasing,
sales, finance (receivables and payables) and reporting**, with role-based access and an
integration API for outside systems such as a POS or a web shop.

**Stack:** Next.js 16 · React 19 · TypeScript · shadcn/ui (Base UI) · TanStack Query · Recharts —
FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL · pytest

All company, people and product data is generated with Faker.

## What it does

| Module | Highlights |
|---|---|
| **Sales** | Customers and groups (default discounts, payment terms, credit limits) · sales orders: draft → confirmed → (partly) delivered → invoiced · credit-limit check on confirmation · stock reservation |
| **Purchasing** | Suppliers · purchase orders: draft → sent → (partly) received · supplier bills matched to what was received (three-way match) |
| **Inventory** | Products with **moving-average cost** · stock per warehouse with *on hand / reserved / available / incoming* · a complete movement ledger · transfers between warehouses · stock counts · reorder points and low-stock alerts |
| **Finance** | Customer invoices and supplier bills · partial payments · overdue tracking · receivables and payables **aging** |
| **Reports** | Dashboard (30-day sales, gross profit, receivables, payables, stock value, low stock, activity) · sales and cost of goods by month · sales by category · top products and customers · stock value per warehouse |
| **Admin** | Users with six roles (admin, manager, sales, purchasing, warehouse, accountant) · API clients · company settings (VAT rate) · an audit trail on every document |
| **Integration API** | Client-credentials tokens · paginated lists that expose only public UUIDs · sales-order import that is **idempotent** on the caller's `external_id` |

Try it with the demo accounts on the login page; each role sees only what it may do.

## Design decisions

- **Stock changes only through the ledger.** Every receipt, delivery, transfer and count posts a
  `stock_move` with its unit cost and source document; `stock_level` is the running sum. A
  database `CHECK` keeps on-hand from going negative, and a delivery that would do so is
  refused with a message saying how much is there.
- **Moving-average costing.** Each receipt blends its cost into the product's average; deliveries
  record the average at shipping time as cost of goods sold, so gross profit is exact per month.
- **Documents follow real workflows.** Orders can be received or delivered in several parts;
  invoices and bills only cover what was actually delivered or received; a cancelled invoice
  frees its quantities to be invoiced again. Confirmed documents can't be edited.
- **Credit control.** Confirming a sales order checks open invoices plus uninvoiced orders against
  the customer's credit limit.
- **Gapless document numbers** (`SO-2026-00042`) from a locked sequence row, safe under concurrency.
- **Permissions, not roles, in the code.** Endpoints ask for `sales.deliver` or `finance.write`;
  roles are just bundles of permissions. The UI hides what a role can't do; the API enforces it.
- **Sessions on the server.** scrypt password hashes, a random session token in an `httpOnly`,
  `SameSite=Lax` cookie with only its SHA-256 stored, lockout after five failed attempts. The
  Next.js app proxies `/api/*` to FastAPI, so the browser only ever talks to one origin.
- **Idempotent integration.** An outside system retrying a sales-order import with the same
  `external_id` gets the first order back instead of a duplicate; a unique constraint backs it
  up when two retries race.
- **Realistic demo data.** A year of history is generated *through the same services the API
  uses* (late payments, short supplier deliveries, store replenishment, supplier backorders),
  so every screen agrees with every other screen.

## Run it locally

Requirements: Python 3.12, Node 20+.

```bash
# backend (SQLite by default)
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements-dev.txt     # macOS/Linux: .venv/bin/pip
cd backend
../.venv/Scripts/python -m erp.cli seed                        # migrate + a year of demo data (~30 s)
../.venv/Scripts/python -m uvicorn app:app --port 8000        # API docs: http://localhost:8000/docs

# frontend, in a second terminal
cd web
npm install
npm run dev                                                   # http://localhost:3000
```

Log in with a demo account (one click on the login page), password `demo1234`.

### Tests

```bash
cd backend
../.venv/Scripts/python -m pytest                                        # SQLite
ERP_TEST_DATABASE_URL=postgresql://... ../.venv/Scripts/python -m pytest # same tests on Postgres
```

The tests drive the HTTP API end to end: purchase-to-pay, order-to-cash, partial deliveries,
moving-average cost, credit limits, transfers and counts, aging, permissions per role, login
lockout and the idempotent import.

## Deploy for free (Vercel + Neon)

Both parts run on Vercel's free Hobby plan; the database on Neon's free tier.

1. **Database.** Create a project at [neon.tech](https://neon.tech) and copy the *pooled*
   connection string.
2. **Schema and demo data**, from your machine:
   ```bash
   cd backend
   ERP_DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require" ../.venv/Scripts/python -m erp.cli seed
   ```
   (`python -m erp.cli migrate` alone creates the schema without demo data;
   `python -m erp.cli create-admin you@company.com "Your Name"` adds a real admin.)
3. **Backend.** In Vercel, *Add New → Project*, import this repository, set **Root Directory** to
   `backend` (Vercel detects FastAPI from `app.py`), and add the environment variables:
   `ERP_DATABASE_URL` (the Neon URL), `ERP_SERVERLESS=true`, `ERP_COOKIE_SECURE=true`.
   Deploy, then check `https://<backend>.vercel.app/api/health`.
4. **Frontend.** Import the same repository again as a second project with **Root Directory**
   `web`, and set `API_URL=https://<backend>.vercel.app`. Deploy and open the URL.

The browser only talks to the frontend domain; Vercel forwards `/api/*` to the backend, so the
login cookie stays first-party.

## Layout

```
backend/
  app.py              entry point (uvicorn / Vercel)
  erp/models/         30 tables: catalog, partners, inventory, purchasing, sales, finance, …
  erp/services/       business rules: inventory ledger, purchasing, sales, finance, reports
  erp/api/            FastAPI routers, one per module (+ integration API)
  erp/seed.py         demo company with a year of history
  migrations/         Alembic
  tests/              end-to-end API tests
web/
  src/app/(erp)/      one folder per module, list / detail / form pages
  src/components/erp/ data table, order form, line editor, dialogs, charts
  src/components/ui/  shadcn/ui components
```
