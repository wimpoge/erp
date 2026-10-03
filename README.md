# ERP

A web app for running a small retail business with several stores and a warehouse:
buying stock, selling to customers, keeping track of inventory, sending invoices and
getting paid.

**Try it:** https://erp-otw7.vercel.app

## How to log in

Click one of the demo roles on the login page, or type a username with the password `demo1234`.

| Username | What this person can do |
|---|---|
| `admin` | Everything, including managing users |
| `manager` | All day-to-day work |
| `sales` | Customers and sales orders |
| `purchasing` | Suppliers and purchase orders |
| `warehouse` | Receiving, shipping, moving and counting stock |
| `finance` | Invoices, bills and payments |

Each role only sees the menus it needs. The demo company, its customers and products are all made up.

## What you can do

**See how the business is doing.** The dashboard shows sales, profit, money owed to and by the
company, stock value and products that are running low.

**Sell.** Create a sales order for a customer, ship it (all at once or in parts), send the
invoice and record the payment. Customers can have a discount group and a credit limit.

**Buy.** Order stock from a supplier, book the goods in when they arrive (even if the supplier
sends less than ordered) and record their bill.

**Manage stock.** See what is in each warehouse and store, move stock between them, and
correct it after a physical count. Every change is kept in a history you can look back on.

**Get paid and pay.** Follow open and overdue invoices and bills, record full or partial
payments, and print a clean A4 invoice with your company details and bank account.

**Look at reports.** Monthly sales and profit, best-selling products, top customers, stock value
per warehouse and who owes what.

**Connect other systems.** A point-of-sale or web shop can read products and stock and send in
orders through an API.

## Built with

Next.js and shadcn/ui for the screens, Python (FastAPI) for the server, and PostgreSQL for
the data. Hosted on Vercel and Neon.

## Run it on your own computer

You need Python 3.12 and Node.js 20 or newer.

```bash
# server, with demo data
python -m venv .venv
.venv/Scripts/pip install -r backend/requirements-dev.txt      # macOS/Linux: .venv/bin/pip
cd backend
../.venv/Scripts/python -m erp.cli seed
../.venv/Scripts/python -m uvicorn app:app --port 8000

# screens, in a second terminal
cd web
npm install
npm run dev
```

Then open http://localhost:3000 and log in as `admin` / `demo1234`.
