from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime, date
from io import BytesIO

from db import get_db_connection
from init_db import init_db
from fpdf import FPDF

import calendar
import os
import sqlite3
import time
import smtplib
import csv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart




app = Flask(__name__)
app.secret_key = "chronofinance_secret_key"

# =========================================================
# EMAIL CONFIG
# =========================================================
EMAIL_ADDRESS = os.environ.get("EMAIL_ADDRESS", "your_email@gmail.com")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "your_app_password")
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "your_email@gmail.com")


# =========================================================
# DATABASE HELPERS
# =========================================================
def execute_with_retry(operation, max_retries=5, delay=0.3):
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
    def wrapped():
        conn = get_db_connection()
        try:
            return query_func(conn)
        finally:
            conn.close()

    return execute_with_retry(wrapped)


def db_write(write_func):
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


def fetch_one_value(cursor, query, values=(), key=None, default=0):
    cursor.execute(query, values)
    row = cursor.fetchone()
    if not row:
        return default
    return row[key] if key else row


def current_user_id():
    return session["user_id"]


def current_username():
    return session["username"]


def write_transaction_to_csv(user_id, category_id, transaction_type, amount, description, transaction_date):
    csv_file = "transactions_backup.csv"
    file_exists = os.path.isfile(csv_file)

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT category_name FROM categories WHERE category_id = ?",
            (category_id,)
        )
        category = cursor.fetchone()
        category_name = category["category_name"] if category else "Unknown"
    finally:
        conn.close()

    with open(csv_file, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)

        if not file_exists:
            writer.writerow([
                "User ID",
                "Category ID",
                "Category Name",
                "Transaction Type",
                "Amount",
                "Description",
                "Transaction Date",
                "Saved At"
            ])

        writer.writerow([
            user_id,
            category_id,
            category_name,
            transaction_type,
            amount,
            description,
            transaction_date,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ])


def ensure_feedback_table():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_messages (
                feedback_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                subject TEXT,
                message TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
    finally:
        conn.close()


def send_feedback_email(name, email, subject, message):
    email_subject = f"ChronoFinance Feedback: {subject if subject else 'No Subject'}"

    email_body = f"""
New feedback received from ChronoFinance

Name: {name}
Email: {email}
Subject: {subject if subject else 'No Subject'}

Message:
{message}
"""

    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = email_subject

    msg.attach(MIMEText(email_body, "plain"))

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
    server.sendmail(EMAIL_ADDRESS, RECEIVER_EMAIL, msg.as_string())
    server.quit()


# =========================================================
# INITIALIZE DB
# =========================================================
try:
    init_db()
    ensure_feedback_table()
except Exception as e:
    print(f"Database initialization error: {e}")


# =========================================================
# AUTH DECORATOR
# =========================================================
def login_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return route_function(*args, **kwargs)

    return wrapper


# =========================================================
# BASIC ROUTES
# =========================================================
@app.route("/")
def home():
    return render_template("index.html")


@app.route("/contact", methods=["POST"])
def contact():
    try:
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            flash("Please fill in name, email, and message.", "error")
            return redirect(url_for("home") + "#contact")

        def write(conn):
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO feedback_messages (name, email, subject, message)
                VALUES (?, ?, ?, ?)
            """, (name, email, subject, message))

        db_write(write)

        try:
            send_feedback_email(name, email, subject, message)
            flash("Your feedback was sent successfully!", "success")
        except Exception as email_error:
            flash(f"Feedback saved, but email failed: {email_error}", "error")

        return redirect(url_for("home") + "#contact")

    except Exception as e:
        flash(f"Error saving feedback: {e}", "error")
        return redirect(url_for("home") + "#contact")


@app.route("/feedbacks")
@login_required
def feedbacks():
    try:
        def query(conn):
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    feedback_id,
                    name,
                    email,
                    subject,
                    message,
                    created_at
                FROM feedback_messages
                ORDER BY created_at DESC, feedback_id DESC
            """)
            return cursor.fetchall()

        all_feedbacks = db_read(query)
        return render_template("feedback.html", feedbacks=all_feedbacks)

    except Exception as e:
        return f"Error: {e}"


@app.route("/test-db")
def test_db():
    try:
        def query(conn):
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            return cursor.fetchall()

        tables = db_read(query)
        return f"Connected successfully. Tables found: {len(tables)}"
    except Exception as e:
        return f"Database connection failed: {e}"


# =========================================================
# AUTH ROUTES
# =========================================================
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

            return "Invalid email or password"

        except Exception as e:
            return f"Error: {e}"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# =========================================================
# DASHBOARD
# =========================================================
@app.route("/dashboard")
@login_required
def dashboard():
    try:
        user_id = current_user_id()

        def query(conn):
            cursor = conn.cursor()

            balance = fetch_one_value(cursor, """
                SELECT COALESCE(SUM(
                    CASE
                        WHEN transaction_type = 'Income' THEN amount
                        WHEN transaction_type = 'Expense' THEN -amount
                        ELSE 0
                    END
                ), 0) AS balance
                FROM finance_transactions
                WHERE user_id = ?
            """, (user_id,), "balance", 0)

            total_income = fetch_one_value(cursor, """
                SELECT COALESCE(SUM(amount), 0) AS total_income
                FROM finance_transactions
                WHERE user_id = ? AND transaction_type = 'Income'
            """, (user_id,), "total_income", 0)

            total_expense = fetch_one_value(cursor, """
                SELECT COALESCE(SUM(amount), 0) AS total_expense
                FROM finance_transactions
                WHERE user_id = ? AND transaction_type = 'Expense'
            """, (user_id,), "total_expense", 0)

            total_transactions = fetch_one_value(cursor, """
                SELECT COUNT(*) AS total_transactions
                FROM finance_transactions
                WHERE user_id = ?
            """, (user_id,), "total_transactions", 0)

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

            current_month = date.today().strftime("%Y-%m")

            month_income = fetch_one_value(cursor, """
                SELECT COALESCE(SUM(amount), 0) AS month_income
                FROM finance_transactions
                WHERE user_id = ?
                  AND transaction_type = 'Income'
                  AND substr(transaction_date, 1, 7) = ?
            """, (user_id, current_month), "month_income", 0)

            month_expense = fetch_one_value(cursor, """
                SELECT COALESCE(SUM(amount), 0) AS month_expense
                FROM finance_transactions
                WHERE user_id = ?
                  AND transaction_type = 'Expense'
                  AND substr(transaction_date, 1, 7) = ?
            """, (user_id, current_month), "month_expense", 0)

            month_savings = month_income - month_expense

            cursor.execute("""
                SELECT monthly_budget, savings_goal
                FROM user_financial_goals
                WHERE user_id = ?
            """, (user_id,))
            goals = cursor.fetchone()

            budget_limit = goals["monthly_budget"] if goals else 10000
            savings_goal = goals["savings_goal"] if goals else 50000

            budget_status = "over" if month_expense > budget_limit else "within"

            savings_progress = 0
            if savings_goal > 0:
                savings_progress = (balance / savings_goal) * 100
                savings_progress = max(0, min(savings_progress, 100))

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

            suggestions = []

            if month_expense > month_income and month_income > 0:
                suggestions.append(
                    "Your expenses are higher than your income this month. Try reducing non-essential spending."
                )

            if budget_limit > 0 and month_expense > (0.8 * budget_limit):
                suggestions.append(
                    "You have already used more than 80% of your monthly budget."
                )

            if total_expense > total_income and total_transactions >= 3:
                suggestions.append(
                    "Your total expenses are greater than your total income. Focus on increasing savings."
                )

            if top_category:
                suggestions.append(
                    f"Your highest spending is in {top_category['category_name']}. Review that category to save more."
                )

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
                "overview_values": overview_values,
                "suggestions": suggestions
            }

        data = db_read(query)

        return render_template(
            "dashboard.html",
            username=current_username(),
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
            overview_values=data["overview_values"],
            suggestions=data["suggestions"]
        )

    except Exception as e:
        return f"Error: {e}"


# =========================================================
# TRANSACTIONS
# =========================================================
@app.route("/add-transaction", methods=["GET", "POST"])
@login_required
def add_transaction():
    try:
        if request.method == "POST":
            category_id = int(request.form["category_id"])
            amount = float(request.form["amount"])
            transaction_type = request.form["transaction_type"]
            description = request.form["description"].strip()
            transaction_date = request.form["transaction_date"]

            def write(conn):
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO finance_transactions
                    (user_id, category_id, transaction_type, amount, description, transaction_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    current_user_id(),
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
                    current_user_id(),
                    category_id,
                    transaction_type,
                    amount,
                    description,
                    transaction_date,
                    "INSERT"
                ))

            user_id = current_user_id()

            db_write(write)

            write_transaction_to_csv(
                user_id=user_id,
                category_id=category_id,
                transaction_type=transaction_type,
                amount=amount,
                description=description,
                transaction_date=transaction_date
            )

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
            values = [current_user_id()]

            if selected_type:
                sql += " AND ft.transaction_type = ?"
                values.append(selected_type)

            if selected_date:
                sql += " AND ft.transaction_date = ?"
                values.append(selected_date)

            if search_query:
                sql += " AND (ft.description LIKE ? OR c.category_name LIKE ?)"
                like_value = f"%{search_query}%"
                values.extend([like_value, like_value])

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
            description = request.form["description"].strip()
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
                    current_user_id()
                ))

                cursor.execute("""
                    INSERT INTO transaction_history
                    (transaction_id, user_id, category_id, transaction_type, amount, description, transaction_date, action_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    transaction_id,
                    current_user_id(),
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
            """, (transaction_id, current_user_id()))
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
            """, (transaction_id, current_user_id()))
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
                """, (transaction_id, current_user_id()))

        db_write(write)
        return redirect(url_for("transactions"))

    except Exception as e:
        return f"Error: {e}"


# =========================================================
# TIME TRAVEL
# =========================================================
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
                """, (current_user_id(), selected_date))
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
                """, (current_user_id(), selected_date))
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


# =========================================================
# HISTORY
# =========================================================
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
            """, (current_user_id(),))
            return cursor.fetchall()

        history_records = db_read(query)
        return render_template("history.html", history_records=history_records)

    except Exception as e:
        return f"Error: {e}"


# =========================================================
# REPORTS
# =========================================================
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

                total_income_local = fetch_one_value(cursor, """
                    SELECT COALESCE(SUM(amount), 0) AS total_income
                    FROM finance_transactions
                    WHERE user_id = ?
                      AND transaction_type = 'Income'
                      AND transaction_date BETWEEN ? AND ?
                """, (current_user_id(), start_date, end_date), "total_income", 0)

                total_expense_local = fetch_one_value(cursor, """
                    SELECT COALESCE(SUM(amount), 0) AS total_expense
                    FROM finance_transactions
                    WHERE user_id = ?
                      AND transaction_type = 'Expense'
                      AND transaction_date BETWEEN ? AND ?
                """, (current_user_id(), start_date, end_date), "total_expense", 0)

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
            """, (current_user_id(),))
            return cursor.fetchall()

        category_data = db_read(query)
        return render_template("category_report.html", category_data=category_data)

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

            total_income_local = fetch_one_value(cursor, """
                SELECT COALESCE(SUM(amount), 0) AS total_income
                FROM finance_transactions
                WHERE user_id = ?
                  AND transaction_type = 'Income'
                  AND transaction_date BETWEEN ? AND ?
            """, (current_user_id(), start_date, end_date), "total_income", 0)

            total_expense_local = fetch_one_value(cursor, """
                SELECT COALESCE(SUM(amount), 0) AS total_expense
                FROM finance_transactions
                WHERE user_id = ?
                  AND transaction_type = 'Expense'
                  AND transaction_date BETWEEN ? AND ?
            """, (current_user_id(), start_date, end_date), "total_expense", 0)

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
        pdf.cell(0, 10, f"User: {current_username()}", ln=True)
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


# =========================================================
# SETTINGS
# =========================================================
@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    try:
        user_id = current_user_id()

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


# =========================================================
# RUN APP
# =========================================================
if __name__ == "__main__":
    app.run(debug=True)