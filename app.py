from flask import Flask, render_template, request, redirect, url_for, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db_connection
from datetime import date
from functools import wraps
from io import BytesIO
from fpdf import FPDF
import calendar
import os
import sqlite3
import time
from init_db import init_db

app = Flask(__name__)
app.secret_key = "chronofinance_secret_key"


# -----------------------------
# Database helpers
# -----------------------------
def execute_with_retry(operation, max_retries=5, delay=0.3):
    """
    Retries DB operation if SQLite reports 'database is locked'
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return operation()
        except sqlite3.OperationalError as e:
            last_error = e
            if "database is locked" in str(e).lower():
                time.sleep(delay * (attempt + 1))
                continue
            raise
    raise last_error


def db_read(query_func):
    """
    For SELECT operations
    """
    def wrapped():
        conn = get_db_connection()
        try:
            result = query_func(conn)
            return result
        finally:
            conn.close()
    return execute_with_retry(wrapped)


def db_write(write_func):
    """
    For INSERT / UPDATE / DELETE operations
    """
    def wrapped():
        conn = get_db_connection()
        try:
            result = write_func(conn)
            conn.commit()
            return result
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    return execute_with_retry(wrapped)


try:
    if os.environ.get("RENDER"):
        init_db()
except Exception as e:
    print(f"Database initialization error: {e}")


# -----------------------------
# Auth helper
# -----------------------------
def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return route_function(*args, **kwargs)
    return wrapper


# -----------------------------
# Routes
# -----------------------------
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/test-db")
def test_db():
    try:
        def query(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            return tables

        tables = db_read(query)
        return f"Connected successfully. Tables found: {len(tables)}"
    except Exception as e:
        return f"Database connection failed: {e}"


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        try:
            def write(conn):
                cursor = conn.cursor()

                cursor.execute(
                    "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                    (username, email, hashed_password)
                )

                user_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO user_financial_goals (user_id, monthly_budget, savings_goal)
                    VALUES (?, ?, ?)
                """, (user_id, 10000, 50000))

            db_write(write)
            return redirect(url_for("login"))

        except Exception as e:
            return f"Error: {e}"

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip()
        password = request.form["password"]

        try:
            def query(conn):
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
                return cursor.fetchone()

            user = db_read(query)

            if user and check_password_hash(user["password"], password):
                session["user_id"] = user["user_id"]
                session["username"] = user["username"]
                return redirect(url_for("dashboard"))
            else:
                return "Invalid email or password"

        except Exception as e:
            return f"Error: {e}"

    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    try:
        user_id = session["user_id"]

        def query(conn):
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COALESCE(SUM(
                    CASE
                        WHEN transaction_type = 'Income' THEN amount
                        WHEN transaction_type = 'Expense' THEN -amount
                        ELSE 0
                    END
                ), 0) AS balance
                FROM finance_transactions
                WHERE user_id = ?
            """, (user_id,))
            balance = cursor.fetchone()["balance"]

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total_income
                FROM finance_transactions
                WHERE user_id = ? AND transaction_type = 'Income'
            """, (user_id,))
            total_income = cursor.fetchone()["total_income"]

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total_expense
                FROM finance_transactions
                WHERE user_id = ? AND transaction_type = 'Expense'
            """, (user_id,))
            total_expense = cursor.fetchone()["total_expense"]

            cursor.execute("""
                SELECT COUNT(*) AS total_transactions
                FROM finance_transactions
                WHERE user_id = ?
            """, (user_id,))
            total_transactions = cursor.fetchone()["total_transactions"]

            cursor.execute("""
                SELECT
                    c.category_name,
                    COALESCE(SUM(ft.amount), 0) AS total_spent
                FROM finance_transactions ft
                JOIN categories c ON ft.category_id = c.category_id
                WHERE ft.user_id = ?
                  AND ft.transaction_type = 'Expense'
                GROUP BY c.category_name
                ORDER BY total_spent DESC
                LIMIT 1
            """, (user_id,))
            top_category = cursor.fetchone()

            today = date.today()
            current_month = today.strftime("%Y-%m")

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS month_income
                FROM finance_transactions
                WHERE user_id = ?
                  AND transaction_type = 'Income'
                  AND substr(transaction_date, 1, 7) = ?
            """, (user_id, current_month))
            month_income = cursor.fetchone()["month_income"]

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS month_expense
                FROM finance_transactions
                WHERE user_id = ?
                  AND transaction_type = 'Expense'
                  AND substr(transaction_date, 1, 7) = ?
            """, (user_id, current_month))
            month_expense = cursor.fetchone()["month_expense"]

            month_savings = month_income - month_expense

            cursor.execute("""
                SELECT monthly_budget, savings_goal
                FROM user_financial_goals
                WHERE user_id = ?
            """, (user_id,))
            goals = cursor.fetchone()

            if goals:
                budget_limit = goals["monthly_budget"]
                savings_goal = goals["savings_goal"]
            else:
                budget_limit = 10000
                savings_goal = 50000

            budget_status = "over" if month_expense > budget_limit else "within"

            if savings_goal > 0:
                savings_progress = (balance / savings_goal) * 100
            else:
                savings_progress = 0

            if savings_progress < 0:
                savings_progress = 0
            if savings_progress > 100:
                savings_progress = 100

            cursor.execute("""
                SELECT
                    ft.transaction_id,
                    ft.transaction_type,
                    ft.amount,
                    ft.description,
                    ft.transaction_date,
                    c.category_name
                FROM finance_transactions ft
                LEFT JOIN categories c ON ft.category_id = c.category_id
                WHERE ft.user_id = ?
                ORDER BY ft.transaction_date DESC, ft.transaction_id DESC
                LIMIT 5
            """, (user_id,))
            recent_transactions = cursor.fetchall()

            cursor.execute("""
                SELECT
                    c.category_name,
                    COALESCE(SUM(ft.amount), 0) AS total_spent
                FROM finance_transactions ft
                JOIN categories c ON ft.category_id = c.category_id
                WHERE ft.user_id = ?
                  AND ft.transaction_type = 'Expense'
                GROUP BY c.category_name
                ORDER BY total_spent DESC
            """, (user_id,))
            category_chart_data = cursor.fetchall()

            category_labels = [row["category_name"] for row in category_chart_data]
            category_values = [float(row["total_spent"]) for row in category_chart_data]

            overview_labels = ["Income", "Expense", "Savings"]
            overview_values = [
                float(month_income),
                float(month_expense),
                float(month_savings)
            ]

            return {
                "balance": balance,
                "total_income": total_income,
                "total_expense": total_expense,
                "total_transactions": total_transactions,
                "top_category": top_category,
                "month_income": month_income,
                "month_expense": month_expense,
                "month_savings": month_savings,
                "budget_limit": budget_limit,
                "budget_status": budget_status,
                "savings_goal": savings_goal,
                "savings_progress": savings_progress,
                "recent_transactions": recent_transactions,
                "category_labels": category_labels,
                "category_values": category_values,
                "overview_labels": overview_labels,
                "overview_values": overview_values
            }

        data = db_read(query)

        return render_template(
            "dashboard.html",
            username=session["username"],
            balance=data["balance"],
            total_income=data["total_income"],
            total_expense=data["total_expense"],
            total_transactions=data["total_transactions"],
            top_category=data["top_category"],
            month_income=data["month_income"],
            month_expense=data["month_expense"],
            month_savings=data["month_savings"],
            budget_limit=data["budget_limit"],
            budget_status=data["budget_status"],
            savings_goal=data["savings_goal"],
            savings_progress=data["savings_progress"],
            recent_transactions=data["recent_transactions"],
            category_labels=data["category_labels"],
            category_values=data["category_values"],
            overview_labels=data["overview_labels"],
            overview_values=data["overview_values"]
        )

    except Exception as e:
        return f"Error: {e}"


@app.route("/add-transaction", methods=["GET", "POST"])
@login_required
def add_transaction():
    try:
        if request.method == "POST":
            category_id = request.form["category_id"]
            amount = float(request.form["amount"])
            transaction_type = request.form["transaction_type"]
            description = request.form["description"]
            transaction_date = request.form["transaction_date"]

            def write(conn):
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO finance_transactions
                    (user_id, category_id, transaction_type, amount, description, transaction_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    session["user_id"],
                    category_id,
                    transaction_type,
                    amount,
                    description,
                    transaction_date
                ))

                transaction_id = cursor.lastrowid

                cursor.execute("""
                    INSERT INTO transaction_history
                    (transaction_id, user_id, category_id, transaction_type, amount, description, transaction_date, action_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    transaction_id,
                    session["user_id"],
                    category_id,
                    transaction_type,
                    amount,
                    description,
                    transaction_date,
                    "INSERT"
                ))

            db_write(write)
            return redirect(url_for("transactions"))

        def query(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM categories ORDER BY category_name ASC")
            return cursor.fetchall()

        categories = db_read(query)
        return render_template("add_transaction.html", categories=categories)

    except Exception as e:
        return f"Error: {e}"


@app.route("/transactions", methods=["GET"])
@login_required
def transactions():
    try:
        selected_type = request.args.get("type", "")
        selected_date = request.args.get("date", "")
        search_query = request.args.get("search", "")

        def query(conn):
            cursor = conn.cursor()

            sql = """
                SELECT
                    ft.transaction_id,
                    ft.transaction_type,
                    ft.amount,
                    ft.description,
                    ft.transaction_date,
                    c.category_name
                FROM finance_transactions ft
                JOIN categories c ON ft.category_id = c.category_id
                WHERE ft.user_id = ?
            """
            values = [session["user_id"]]

            if selected_type:
                sql += " AND ft.transaction_type = ?"
                values.append(selected_type)

            if selected_date:
                sql += " AND ft.transaction_date = ?"
                values.append(selected_date)

            if search_query:
                sql += " AND (ft.description LIKE ? OR c.category_name LIKE ?)"
                like_value = f"%{search_query}%"
                values.append(like_value)
                values.append(like_value)

            sql += " ORDER BY ft.transaction_date DESC, ft.transaction_id DESC"

            cursor.execute(sql, tuple(values))
            return cursor.fetchall()

        all_transactions = db_read(query)

        return render_template(
            "transactions.html",
            transactions=all_transactions,
            selected_type=selected_type,
            selected_date=selected_date,
            search_query=search_query
        )

    except Exception as e:
        return f"Error: {e}"


@app.route("/edit-transaction/<int:transaction_id>", methods=["GET", "POST"])
@login_required
def edit_transaction(transaction_id):
    try:
        if request.method == "POST":
            category_id = request.form["category_id"]
            amount = float(request.form["amount"])
            transaction_type = request.form["transaction_type"]
            description = request.form["description"]
            transaction_date = request.form["transaction_date"]

            def write(conn):
                cursor = conn.cursor()

                cursor.execute("""
                    UPDATE finance_transactions
                    SET category_id = ?,
                        amount = ?,
                        transaction_type = ?,
                        description = ?,
                        transaction_date = ?
                    WHERE transaction_id = ? AND user_id = ?
                """, (
                    category_id,
                    amount,
                    transaction_type,
                    description,
                    transaction_date,
                    transaction_id,
                    session["user_id"]
                ))

                cursor.execute("""
                    INSERT INTO transaction_history
                    (transaction_id, user_id, category_id, transaction_type, amount, description, transaction_date, action_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    transaction_id,
                    session["user_id"],
                    category_id,
                    transaction_type,
                    amount,
                    description,
                    transaction_date,
                    "UPDATE"
                ))

            db_write(write)
            return redirect(url_for("transactions"))

        def query(conn):
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM categories ORDER BY category_name ASC")
            categories = cursor.fetchall()

            cursor.execute("""
                SELECT *
                FROM finance_transactions
                WHERE transaction_id = ? AND user_id = ?
            """, (transaction_id, session["user_id"]))
            transaction = cursor.fetchone()

            return categories, transaction

        categories, transaction = db_read(query)

        if not transaction:
            return "Transaction not found"

        return render_template(
            "edit_transaction.html",
            transaction=transaction,
            categories=categories
        )

    except Exception as e:
        return f"Error: {e}"


@app.route("/delete-transaction/<int:transaction_id>")
@login_required
def delete_transaction(transaction_id):
    try:
        def write(conn):
            cursor = conn.cursor()

            cursor.execute("""
                SELECT *
                FROM finance_transactions
                WHERE transaction_id = ? AND user_id = ?
            """, (transaction_id, session["user_id"]))
            transaction = cursor.fetchone()

            if transaction:
                cursor.execute("""
                    INSERT INTO transaction_history
                    (transaction_id, user_id, category_id, transaction_type, amount, description, transaction_date, action_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    transaction["transaction_id"],
                    transaction["user_id"],
                    transaction["category_id"],
                    transaction["transaction_type"],
                    transaction["amount"],
                    transaction["description"],
                    transaction["transaction_date"],
                    "DELETE"
                ))

                cursor.execute("""
                    DELETE FROM finance_transactions
                    WHERE transaction_id = ? AND user_id = ?
                """, (transaction_id, session["user_id"]))

        db_write(write)
        return redirect(url_for("transactions"))

    except Exception as e:
        return f"Error: {e}"


@app.route("/time-travel", methods=["GET", "POST"])
@login_required
def time_travel():
    balance_on_date = None
    selected_date = ""
    filtered_transactions = []

    try:
        if request.method == "POST":
            selected_date = request.form["selected_date"]

            def query(conn):
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT
                        COALESCE(SUM(
                            CASE
                                WHEN transaction_type = 'Income' THEN amount
                                WHEN transaction_type = 'Expense' THEN -amount
                                ELSE 0
                            END
                        ), 0) AS balance_on_date
                    FROM finance_transactions
                    WHERE user_id = ? AND transaction_date <= ?
                """, (session["user_id"], selected_date))
                balance_on_date_local = cursor.fetchone()["balance_on_date"]

                cursor.execute("""
                    SELECT
                        ft.transaction_id,
                        ft.transaction_type,
                        ft.amount,
                        ft.description,
                        ft.transaction_date,
                        c.category_name
                    FROM finance_transactions ft
                    JOIN categories c ON ft.category_id = c.category_id
                    WHERE ft.user_id = ? AND ft.transaction_date <= ?
                    ORDER BY ft.transaction_date DESC, ft.transaction_id DESC
                """, (session["user_id"], selected_date))
                filtered_transactions_local = cursor.fetchall()

                return balance_on_date_local, filtered_transactions_local

            balance_on_date, filtered_transactions = db_read(query)

        return render_template(
            "time_travel.html",
            balance_on_date=balance_on_date,
            selected_date=selected_date,
            filtered_transactions=filtered_transactions
        )

    except Exception as e:
        return f"Error: {e}"


@app.route("/history")
@login_required
def history():
    try:
        def query(conn):
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    th.history_id,
                    th.transaction_id,
                    th.transaction_type,
                    th.amount,
                    th.description,
                    th.transaction_date,
                    th.action_type,
                    th.changed_at,
                    c.category_name
                FROM transaction_history th
                LEFT JOIN categories c ON th.category_id = c.category_id
                WHERE th.user_id = ?
                ORDER BY th.changed_at DESC, th.history_id DESC
            """, (session["user_id"],))
            return cursor.fetchall()

        history_records = db_read(query)
        return render_template("history.html", history_records=history_records)

    except Exception as e:
        return f"Error: {e}"


@app.route("/monthly-report", methods=["GET", "POST"])
@login_required
def monthly_report():
    total_income = 0
    total_expense = 0
    savings = 0
    selected_month = ""

    try:
        if request.method == "POST":
            selected_month = request.form["selected_month"]

            year, month = map(int, selected_month.split("-"))
            start_date = f"{year}-{month:02d}-01"
            last_day = calendar.monthrange(year, month)[1]
            end_date = f"{year}-{month:02d}-{last_day:02d}"

            def query(conn):
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT COALESCE(SUM(amount), 0) AS total_income
                    FROM finance_transactions
                    WHERE user_id = ?
                      AND transaction_type = 'Income'
                      AND transaction_date BETWEEN ? AND ?
                """, (session["user_id"], start_date, end_date))
                total_income_local = cursor.fetchone()["total_income"]

                cursor.execute("""
                    SELECT COALESCE(SUM(amount), 0) AS total_expense
                    FROM finance_transactions
                    WHERE user_id = ?
                      AND transaction_type = 'Expense'
                      AND transaction_date BETWEEN ? AND ?
                """, (session["user_id"], start_date, end_date))
                total_expense_local = cursor.fetchone()["total_expense"]

                return total_income_local, total_expense_local

            total_income, total_expense = db_read(query)
            savings = total_income - total_expense

        return render_template(
            "monthly_report.html",
            total_income=total_income,
            total_expense=total_expense,
            savings=savings,
            selected_month=selected_month
        )

    except Exception as e:
        return f"Error: {e}"


@app.route("/category-report")
@login_required
def category_report():
    try:
        def query(conn):
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    c.category_name,
                    COALESCE(SUM(ft.amount), 0) AS total_spent
                FROM finance_transactions ft
                JOIN categories c ON ft.category_id = c.category_id
                WHERE ft.user_id = ?
                  AND ft.transaction_type = 'Expense'
                GROUP BY c.category_name
                ORDER BY total_spent DESC
            """, (session["user_id"],))
            return cursor.fetchall()

        category_data = db_read(query)
        return render_template("category_report.html", category_data=category_data)

    except Exception as e:
        return f"Error: {e}"


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    try:
        user_id = session["user_id"]

        if request.method == "POST":
            monthly_budget = float(request.form["monthly_budget"])
            savings_goal = float(request.form["savings_goal"])

            if monthly_budget < 0 or savings_goal < 0:
                return "Budget and savings goal cannot be negative"

            def write(conn):
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE user_financial_goals
                    SET monthly_budget = ?, savings_goal = ?
                    WHERE user_id = ?
                """, (monthly_budget, savings_goal, user_id))

            db_write(write)
            return redirect(url_for("dashboard"))

        def query(conn):
            cursor = conn.cursor()
            cursor.execute("""
                SELECT monthly_budget, savings_goal
                FROM user_financial_goals
                WHERE user_id = ?
            """, (user_id,))
            return cursor.fetchone()

        goals = db_read(query)
        return render_template("settings.html", goals=goals)

    except Exception as e:
        return f"Error: {e}"


@app.route("/monthly-report/pdf/<selected_month>")
@login_required
def monthly_report_pdf(selected_month):
    try:
        year, month = map(int, selected_month.split("-"))
        start_date = f"{year}-{month:02d}-01"
        last_day = calendar.monthrange(year, month)[1]
        end_date = f"{year}-{month:02d}-{last_day:02d}"

        def query(conn):
            cursor = conn.cursor()

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total_income
                FROM finance_transactions
                WHERE user_id = ?
                  AND transaction_type = 'Income'
                  AND transaction_date BETWEEN ? AND ?
            """, (session["user_id"], start_date, end_date))
            total_income_local = cursor.fetchone()["total_income"]

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total_expense
                FROM finance_transactions
                WHERE user_id = ?
                  AND transaction_type = 'Expense'
                  AND transaction_date BETWEEN ? AND ?
            """, (session["user_id"], start_date, end_date))
            total_expense_local = cursor.fetchone()["total_expense"]

            return total_income_local, total_expense_local

        total_income, total_expense = db_read(query)
        savings = total_income - total_expense

        pdf = FPDF()
        pdf.add_page()
        pdf.set_auto_page_break(auto=True, margin=15)

        pdf.set_font("Arial", "B", 18)
        pdf.cell(0, 12, "ChronoFinance Monthly Report", ln=True, align="C")

        pdf.ln(8)
        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"User: {session['username']}", ln=True)
        pdf.cell(0, 10, f"Month: {selected_month}", ln=True)

        pdf.ln(5)
        pdf.set_font("Arial", "B", 13)
        pdf.cell(0, 10, "Report Summary", ln=True)

        pdf.set_font("Arial", "", 12)
        pdf.cell(0, 10, f"Total Income: Rs. {total_income}", ln=True)
        pdf.cell(0, 10, f"Total Expense: Rs. {total_expense}", ln=True)
        pdf.cell(0, 10, f"Savings: Rs. {savings}", ln=True)

        if savings > 0:
            status = "Good saving month"
        elif savings == 0:
            status = "Balanced month"
        else:
            status = "Expenses exceeded income"

        pdf.ln(5)
        pdf.cell(0, 10, f"Status: {status}", ln=True)

        pdf_output = bytes(pdf.output(dest="S"))
        pdf_buffer = BytesIO(pdf_output)
        pdf_buffer.seek(0)

        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"monthly_report_{selected_month}.pdf",
            mimetype="application/pdf"
        )

    except Exception as e:
        return f"Error: {e}"


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)