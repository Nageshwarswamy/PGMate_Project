from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from urllib.parse import quote

import mysql.connector
import qrcode
from flask import Flask, flash, redirect, render_template, request, send_file, url_for

app = Flask(__name__)
app.secret_key = "change-this-secret-key-before-deployment"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "Bengaluru@1308",
    "database": "pgmate",
}

def db():
    return mysql.connector.connect(**DB_CONFIG)

def money(value):
    try:
        return Decimal(str(value or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        return Decimal("0.00")

def months_charged(start, end):
    """Completed monthly anniversaries plus one full month for any partial period."""
    if not start or not end or end < start:
        return 0
    months = (end.year - start.year) * 12 + end.month - start.month
    if end.day > start.day:
        months += 1
    return max(1, months)

def migrate():
    """Safe, repeatable migration: adds new columns/tables without deleting existing data."""
    conn = db()
    cur = conn.cursor()
    cur.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA=%s AND TABLE_NAME='residents'
    """, (DB_CONFIG["database"],))
    existing = {row[0] for row in cur.fetchall()}
    additions = {
        "monthly_rent": "DECIMAL(10,2) NOT NULL DEFAULT 0",
        "security_deposit": "DECIMAL(10,2) NOT NULL DEFAULT 0",
        "maintenance_fee": "DECIMAL(10,2) NOT NULL DEFAULT 0",
        "advance_amount": "DECIMAL(10,2) NOT NULL DEFAULT 0",
        "notice_date": "DATE NULL",
    }
    for column, definition in additions.items():
        if column not in existing:
            cur.execute(f"ALTER TABLE residents ADD COLUMN {column} {definition}")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id INT AUTO_INCREMENT PRIMARY KEY,
            resident_id INT NOT NULL,
            transaction_type VARCHAR(40) NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            transaction_date DATE NOT NULL,
            payment_method VARCHAR(40) DEFAULT 'Cash',
            reference_number VARCHAR(100) NULL,
            notes VARCHAR(500) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (resident_id) REFERENCES residents(resident_id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS pg_settings (
            setting_key VARCHAR(80) PRIMARY KEY,
            setting_value VARCHAR(255) NOT NULL DEFAULT ''
        )
    """)
    cur.execute("""
        INSERT IGNORE INTO pg_settings(setting_key, setting_value)
        VALUES ('pg_name', 'PGMate'), ('upi_id', '')
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS final_settlements (
            settlement_id INT AUTO_INCREMENT PRIMARY KEY,
            resident_id INT NOT NULL,
            joining_date DATE NOT NULL,
            leaving_date DATE NOT NULL,
            notice_date DATE NULL,
            notice_days INT NOT NULL DEFAULT 0,
            months_charged INT NOT NULL DEFAULT 0,
            monthly_rent DECIMAL(10,2) NOT NULL DEFAULT 0,
            rent_due DECIMAL(10,2) NOT NULL DEFAULT 0,
            rent_paid DECIMAL(10,2) NOT NULL DEFAULT 0,
            advance_credit DECIMAL(10,2) NOT NULL DEFAULT 0,
            security_deposit DECIMAL(10,2) NOT NULL DEFAULT 0,
            maintenance_fee DECIMAL(10,2) NOT NULL DEFAULT 0,
            other_deductions DECIMAL(10,2) NOT NULL DEFAULT 0,
            deposit_refund_eligible TINYINT(1) NOT NULL DEFAULT 0,
            refund_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
            balance_due DECIMAL(10,2) NOT NULL DEFAULT 0,
            refund_paid TINYINT(1) NOT NULL DEFAULT 0,
            notes VARCHAR(500) NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (resident_id) REFERENCES residents(resident_id)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def get_settings():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT setting_key, setting_value FROM pg_settings")
    settings = dict(cur.fetchall())
    cur.close()
    conn.close()
    return settings

@app.context_processor
def inject_settings():
    try:
        return {"site_settings": get_settings()}
    except Exception:
        return {"site_settings": {"pg_name": "PGMate", "upi_id": ""}}

@app.route("/")
def dashboard():
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT r.*,
          COALESCE((SELECT SUM(amount) FROM rent_payments p WHERE p.resident_id=r.resident_id AND p.status='Paid'),0) AS rent_paid,
          COALESCE((SELECT SUM(amount) FROM rent_payments p WHERE p.resident_id=r.resident_id AND p.status='Pending'),0) AS rent_pending
        FROM residents r
        ORDER BY (r.leaving_date IS NOT NULL), r.name
    """)
    residents = cur.fetchall()
    cur.execute("SELECT COUNT(*) total FROM residents WHERE leaving_date IS NULL")
    active = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) total FROM residents WHERE leaving_date IS NOT NULL")
    past = cur.fetchone()["total"]
    cur.execute("SELECT COALESCE(SUM(amount),0) total FROM rent_payments WHERE status='Paid'")
    rent_collected = cur.fetchone()["total"]
    cur.execute("SELECT COALESCE(SUM(amount),0) total FROM rent_payments WHERE status='Pending'")
    rent_pending = cur.fetchone()["total"]
    cur.execute("SELECT COALESCE(SUM(security_deposit),0) total FROM residents WHERE leaving_date IS NULL")
    deposits = cur.fetchone()["total"]
    cur.execute("SELECT COALESCE(SUM(maintenance_fee),0) total FROM residents")
    maintenance = cur.fetchone()["total"]
    cur.execute("SELECT COUNT(*) total FROM residents WHERE leaving_date IS NULL")
    occupied = cur.fetchone()["total"]
    cur.close()
    conn.close()
    return render_template("dashboard.html", residents=residents, active=active, past=past,
        rent_collected=rent_collected, rent_pending=rent_pending, deposits=deposits,
        maintenance=maintenance, occupied=occupied)

@app.route("/residents/add", methods=["GET", "POST"])
def add_resident():
    if request.method == "POST":
        name = request.form["name"].strip()
        phone = request.form["phone"].strip()
        room = request.form["room_number"].strip()
        joining = request.form["joining_date"]
        monthly = money(request.form.get("monthly_rent"))
        deposit = money(request.form.get("security_deposit"))
        maintenance = money(request.form.get("maintenance_fee"))
        advance = money(request.form.get("advance_amount"))
        if not name or not phone or not room or not joining:
            flash("Please complete all required resident details.", "error")
            return redirect(url_for("add_resident"))
        conn = db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO residents(name,phone,room_number,joining_date,monthly_rent,
                security_deposit,maintenance_fee,advance_amount)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
        """, (name, phone, room, joining, monthly, deposit, maintenance, advance))
        rid = cur.lastrowid
        for kind, amount in [("Security Deposit", deposit), ("Maintenance", maintenance), ("Advance Rent", advance)]:
            if amount > 0:
                cur.execute("""
                    INSERT INTO transactions(resident_id,transaction_type,amount,transaction_date,notes)
                    VALUES(%s,%s,%s,%s,%s)
                """, (rid, kind, amount, joining, "Initial amount recorded at joining"))
        conn.commit()
        cur.close()
        conn.close()
        flash("Resident added with initial financial details.", "success")
        return redirect(url_for("dashboard"))
    return render_template("resident_form.html", resident=None)

@app.route("/residents/<int:rid>/edit", methods=["GET", "POST"])
def edit_resident(rid):
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM residents WHERE resident_id=%s", (rid,))
    resident = cur.fetchone()
    if not resident:
        cur.close(); conn.close()
        flash("Resident not found.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        cur.execute("""
            UPDATE residents SET name=%s, phone=%s, room_number=%s, joining_date=%s,
                monthly_rent=%s, security_deposit=%s, maintenance_fee=%s
            WHERE resident_id=%s
        """, (request.form["name"].strip(), request.form["phone"].strip(),
              request.form["room_number"].strip(), request.form["joining_date"],
              money(request.form.get("monthly_rent")), money(request.form.get("security_deposit")),
              money(request.form.get("maintenance_fee")), rid))
        conn.commit()
        cur.close(); conn.close()
        flash("Resident details updated. Existing transaction history is unchanged.", "success")
        return redirect(url_for("dashboard"))
    cur.close(); conn.close()
    return render_template("resident_form.html", resident=resident)

@app.route("/residents/<int:rid>")
def resident_detail(rid):
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM residents WHERE resident_id=%s", (rid,))
    resident = cur.fetchone()
    if not resident:
        cur.close(); conn.close()
        flash("Resident not found.", "error")
        return redirect(url_for("dashboard"))
    cur.execute("SELECT * FROM rent_payments WHERE resident_id=%s ORDER BY payment_date DESC", (rid,))
    rents = cur.fetchall()
    cur.execute("SELECT * FROM transactions WHERE resident_id=%s ORDER BY transaction_date DESC, transaction_id DESC", (rid,))
    transactions = cur.fetchall()
    cur.execute("SELECT * FROM final_settlements WHERE resident_id=%s ORDER BY settlement_id DESC", (rid,))
    settlements = cur.fetchall()
    cur.close(); conn.close()
    return render_template("resident_detail.html", resident=resident, rents=rents,
                           transactions=transactions, settlements=settlements)

@app.route("/rent/add", methods=["GET", "POST"])
def add_rent():
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT resident_id,name,room_number FROM residents WHERE leaving_date IS NULL ORDER BY name")
    residents = cur.fetchall()
    if request.method == "POST":
        rid = int(request.form["resident_id"])
        amount = money(request.form["amount"])
        pay_date = request.form["payment_date"]
        status = request.form["status"]
        conn2 = conn.cursor()
        conn2.execute("""
            INSERT INTO rent_payments(resident_id,rent_month,amount,payment_date,status)
            VALUES(%s,%s,%s,%s,%s)
        """, (rid, request.form["rent_month"], amount, pay_date, status))
        if status == "Paid":
            conn2.execute("""
                INSERT INTO transactions(resident_id,transaction_type,amount,transaction_date,
                    payment_method,reference_number,notes)
                VALUES(%s,'Rent',%s,%s,%s,%s,%s)
            """, (rid, amount, pay_date, request.form.get("payment_method","Cash"),
                  request.form.get("reference_number",""), "Rent payment"))
        conn.commit()
        conn2.close(); cur.close(); conn.close()
        flash("Rent entry saved.", "success")
        return redirect(url_for("rent_history"))
    cur.close(); conn.close()
    return render_template("rent_form.html", residents=residents, today=date.today().isoformat())

@app.route("/rent")
def rent_history():
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT p.*,r.name,r.room_number FROM rent_payments p
        JOIN residents r ON r.resident_id=p.resident_id
        ORDER BY p.payment_date DESC,p.payment_id DESC
    """)
    payments = cur.fetchall()
    cur.close(); conn.close()
    return render_template("rent_history.html", payments=payments)

@app.route("/transactions")
def transactions():
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT t.*,r.name,r.room_number FROM transactions t
        JOIN residents r ON r.resident_id=t.resident_id
        ORDER BY t.transaction_date DESC,t.transaction_id DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return render_template("transactions.html", rows=rows)

@app.route("/vacate/<int:rid>", methods=["GET", "POST"])
def vacate(rid):
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM residents WHERE resident_id=%s", (rid,))
    resident = cur.fetchone()
    if not resident or resident["leaving_date"]:
        cur.close(); conn.close()
        flash("Active resident not found.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        leaving = date.fromisoformat(request.form["leaving_date"])
        notice_raw = request.form.get("notice_date") or ""
        notice = date.fromisoformat(notice_raw) if notice_raw else None
        if leaving < resident["joining_date"]:
            flash("Leaving date cannot be before joining date.", "error")
            cur.close(); conn.close()
            return redirect(url_for("vacate", rid=rid))
        notice_days = (leaving - notice).days if notice else 0
        months = months_charged(resident["joining_date"], leaving)
        monthly = money(resident["monthly_rent"])
        rent_due = monthly * months
        cur.execute("SELECT COALESCE(SUM(amount),0) total FROM rent_payments WHERE resident_id=%s AND status='Paid'", (rid,))
        rent_paid = money(cur.fetchone()["total"])
        advance = money(resident["advance_amount"])
        total_credit = rent_paid + advance
        rent_shortfall = max(Decimal("0.00"), rent_due - total_credit)
        deposit = money(resident["security_deposit"])
        notice_ok = bool(notice and notice_days >= 15)
        other = money(request.form.get("other_deductions"))
        refundable_deposit = deposit if notice_ok else Decimal("0.00")
        refund = max(Decimal("0.00"), refundable_deposit - rent_shortfall - other)
        balance_due = max(Decimal("0.00"), rent_shortfall + other - refundable_deposit)
        notes = request.form.get("notes","").strip()
        cur2 = conn.cursor()
        cur2.execute("""
            INSERT INTO final_settlements(resident_id,joining_date,leaving_date,notice_date,
                notice_days,months_charged,monthly_rent,rent_due,rent_paid,advance_credit,
                security_deposit,maintenance_fee,other_deductions,deposit_refund_eligible,
                refund_amount,balance_due,notes)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (rid,resident["joining_date"],leaving,notice,notice_days,months,monthly,
              rent_due,rent_paid,advance,deposit,money(resident["maintenance_fee"]),
              other,int(notice_ok),refund,balance_due,notes))
        cur2.execute("UPDATE residents SET notice_date=%s, leaving_date=%s WHERE resident_id=%s",
                     (notice,leaving,rid))
        conn.commit()
        cur2.close(); cur.close(); conn.close()
        return redirect(url_for("settlement_bill", rid=rid))
    cur.close(); conn.close()
    return render_template("vacate_form.html", resident=resident, today=date.today().isoformat())

@app.route("/settlement/<int:rid>")
def settlement_bill(rid):
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT s.*,r.name,r.phone,r.room_number
        FROM final_settlements s JOIN residents r ON r.resident_id=s.resident_id
        WHERE s.resident_id=%s ORDER BY s.settlement_id DESC LIMIT 1
    """, (rid,))
    bill = cur.fetchone()
    cur.close(); conn.close()
    if not bill:
        flash("No final settlement found.", "error")
        return redirect(url_for("dashboard"))
    return render_template("settlement.html", bill=bill)

@app.route("/settlement/<int:settlement_id>/refund-paid", methods=["POST"])
def mark_refund_paid(settlement_id):
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM final_settlements WHERE settlement_id=%s", (settlement_id,))
    settlement = cur.fetchone()
    if settlement:
        cur2 = conn.cursor()
        cur2.execute("UPDATE final_settlements SET refund_paid=1 WHERE settlement_id=%s", (settlement_id,))
        if settlement["refund_amount"] > 0:
            cur2.execute("""
                INSERT INTO transactions(resident_id,transaction_type,amount,transaction_date,
                    payment_method,notes)
                VALUES(%s,'Deposit Refund',%s,%s,%s,%s)
            """, (settlement["resident_id"], settlement["refund_amount"], date.today(),
                  request.form.get("payment_method","UPI"), "Security deposit refund paid"))
        conn.commit()
        cur2.close()
    cur.close(); conn.close()
    flash("Refund marked as paid.", "success")
    return redirect(url_for("settlement_bill", rid=settlement["resident_id"]))

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        conn = db()
        cur = conn.cursor()
        cur.execute("INSERT INTO pg_settings(setting_key,setting_value) VALUES('pg_name',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
                    (request.form.get("pg_name","PGMate").strip() or "PGMate",))
        cur.execute("INSERT INTO pg_settings(setting_key,setting_value) VALUES('upi_id',%s) ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)",
                    (request.form.get("upi_id","").strip(),))
        conn.commit(); cur.close(); conn.close()
        flash("PG settings saved.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", settings=get_settings())

@app.route("/payment-qr")
def payment_qr():
    upi_id = get_settings().get("upi_id","").strip()
    if not upi_id:
        return "UPI ID is not configured yet. Add it in PG Settings.", 400
    amount = request.args.get("amount","").strip()
    name = get_settings().get("pg_name","PGMate")
    params = f"pa={quote(upi_id)}&pn={quote(name)}&cu=INR"
    if amount:
        params += f"&am={quote(amount)}"
    qr = qrcode.make(f"upi://pay?{params}")
    output = BytesIO()
    qr.save(output, format="PNG")
    output.seek(0)
    return send_file(output, mimetype="image/png")

@app.route("/past-members")
def past_members():
    conn = db()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT r.*,s.settlement_id,s.refund_amount,s.refund_paid,s.balance_due
        FROM residents r LEFT JOIN (
            SELECT fs1.* FROM final_settlements fs1
            INNER JOIN (SELECT resident_id,MAX(settlement_id) sid FROM final_settlements GROUP BY resident_id) latest
            ON latest.sid=fs1.settlement_id
        ) s ON s.resident_id=r.resident_id
        WHERE r.leaving_date IS NOT NULL ORDER BY r.leaving_date DESC
    """)
    residents = cur.fetchall()
    cur.close(); conn.close()
    return render_template("past_members.html", residents=residents)

if __name__ == "__main__":
    migrate()
    app.run(debug=True)
