# PGMate — PG Management & Accounting

Flask + MySQL application for resident management, rent collection, deposits, maintenance, UPI QR display and resident exit settlement.

## Important rules configured
- Partial month: charge a full month's rent for any started partial monthly period.
- Maintenance: one-time and non-refundable.
- Security deposit: refundable only when at least 15 days' notice is given.
- Advance rent: credited against rent due in the final settlement.
- Residents are marked as Left, not deleted. Their history is retained.
- UPI ID is not configured yet; add it later in PG Settings.

## Existing project upgrade (preserve your data)
1. Back up your `pgmate` database in MySQL Workbench: Server → Data Export → select `pgmate` → Export to Self-Contained File → Start Export.
2. Extract this ZIP into a new folder.
3. Copy your existing MySQL password into `DB_CONFIG` in `app.py`.
4. Do NOT run `schema.sql` over your existing project as a replacement. Your existing tables already exist.
5. Run `python app.py`. The app runs a repeatable migration that adds missing columns and creates the new tables without dropping existing resident or rent records.
6. If you want to start a brand-new database instead, execute `schema.sql` in MySQL Workbench first.

## Install and run (Windows PowerShell)
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

If PowerShell blocks activation:
```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe app.py
```

## Modules
- Dashboard: active/past residents, rent collection, pending rent, deposits held, maintenance recorded.
- Current residents: create/edit/view resident details.
- Resident finances: monthly rent, security deposit, one-time maintenance, advance rent.
- Rent records: paid and pending entries.
- Transactions: initial collection and recorded rent receipts.
- Vacating: enter notice date, leaving date and other deductions.
- Final settlement: printable final statement with rent duration, rent due, rent paid, advance credit, deposit eligibility, maintenance and refund/balance.
- Past Members: former residents and settlement status.
- PG Settings: PG display name and UPI ID. QR is generated after UPI ID is configured.

## Calculation details
The rent-month calculation uses monthly anniversaries. Completed monthly periods are counted, and if the leaving date falls after the latest monthly anniversary, one additional full month is charged. For example, 4 completed months plus 10 extra days is billed as 5 months.
The 15-day notice rule is checked using `leaving date - notice date >= 15`.
The deposit refund is calculated as: eligible security deposit − unpaid rent after paid rent and advance credit − other deductions, with a minimum refund of zero. If deductions exceed the eligible deposit, the remaining amount is shown as balance due.
Maintenance is displayed on the settlement but never added to the refundable amount.
This is a starter accounting workflow. Confirm local tenancy/consumer rules and your written PG agreement before using it for actual disputes or refunds.

## Notes about existing residents
The migration preserves old records. Existing residents will have monthly rent, deposit, maintenance and advance set to 0 until you edit their profiles and enter the actual agreed amounts. Old rent payment rows remain available.
The old app's existing residents do not automatically get initial transaction rows; enter new collection records only when actually received to avoid duplicate accounting.
