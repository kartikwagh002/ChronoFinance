from flask import Flask, render_template, request, redirect, url_for, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from db import get_db_connection
from datetime import date
import calendar
from io import BytesIO
from fpdf import FPDF

app = Flask(__name__)
app.secret_key = "chronofinance_secret_key"


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/test-db")
def test_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(buffered=True)
        cursor.execute("SELECT DATABASE();")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return f"Connected successfully to database: {result[0]}"
    except Exception as e:
        return f"Database connection failed: {e}"


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]

        hashed_password = generate_password_hash(password)

        try:
            conn = get_db_connection()
            cursor = conn.cursor(buffered=True)

            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
                (username, email, hashed_password)
            )

            user_id = cursor.lastrowid

            cursor.execute("""
                INSERT INTO user_financial_goals (user_id, monthly_budget, savings_goal)
                VALUES (%s, %s, %s)
            """, (user_id, 10000, 50000))

            conn.commit()
            cursor.close()
            conn.close()

            return redirect(url_for("login"))

        except Exception as e:
            return f"Error: {e}"

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)

            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()

            cursor.close()
            conn.close()

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
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        user_id = session["user_id"]

        cursor.execute("""
            SELECT COALESCE(SUM(
                CASE
                    WHEN transaction_type = 'Income' THEN amount
                    WHEN transaction_type = 'Expense' THEN -amount
                    ELSE 0
                END
            ), 0) AS balance
            FROM finance_transactions
            WHERE user_id = %s
        """, (user_id,))
        balance = cursor.fetchone()["balance"]

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_income
            FROM finance_transactions
            WHERE user_id = %s AND transaction_type = 'Income'
        """, (user_id,))
        total_income = cursor.fetchone()["total_income"]

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_expense
            FROM finance_transactions
            WHERE user_id = %s AND transaction_type = 'Expense'
        """, (user_id,))
        total_expense = cursor.fetchone()["total_expense"]

        cursor.execute("""
            SELECT COUNT(*) AS total_transactions
            FROM finance_transactions
            WHERE user_id = %s
        """, (user_id,))
        total_transactions = cursor.fetchone()["total_transactions"]

        cursor.execute("""
            SELECT
                c.category_name,
                COALESCE(SUM(ft.amount), 0) AS total_spent
            FROM finance_transactions ft
            JOIN categories c ON ft.category_id = c.category_id
            WHERE ft.user_id = %s
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
            WHERE user_id = %s
              AND transaction_type = 'Income'
              AND DATE_FORMAT(transaction_date, '%%Y-%%m') = %s
        """, (user_id, current_month))
        month_income = cursor.fetchone()["month_income"]

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS month_expense
            FROM finance_transactions
            WHERE user_id = %s
              AND transaction_type = 'Expense'
              AND DATE_FORMAT(transaction_date, '%%Y-%%m') = %s
        """, (user_id, current_month))
        month_expense = cursor.fetchone()["month_expense"]

        month_savings = month_income - month_expense

        cursor.execute("""
            SELECT monthly_budget, savings_goal
            FROM user_financial_goals
            WHERE user_id = %s
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
            WHERE ft.user_id = %s
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
            WHERE ft.user_id = %s
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

        cursor.close()
        conn.close()

        return render_template(
            "dashboard.html",
            username=session["username"],
            balance=balance,
            total_income=total_income,
            total_expense=total_expense,
            total_transactions=total_transactions,
            top_category=top_category,
            month_income=month_income,
            month_expense=month_expense,
            month_savings=month_savings,
            budget_limit=budget_limit,
            budget_status=budget_status,
            savings_goal=savings_goal,
            savings_progress=savings_progress,
            recent_transactions=recent_transactions,
            category_labels=category_labels,
            category_values=category_values,
            overview_labels=overview_labels,
            overview_values=overview_values
        )

    except Exception as e:
        return f"Error: {e}"


@app.route("/transactions", methods=["GET"])
def transactions():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        selected_type = request.args.get("type", "")
        selected_date = request.args.get("date", "")
        search_query = request.args.get("search", "")

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
            WHERE ft.user_id = %s
        """
        values = [session["user_id"]]

        if selected_type:
            sql += " AND ft.transaction_type = %s"
            values.append(selected_type)

        if selected_date:
            sql += " AND ft.transaction_date = %s"
            values.append(selected_date)

        if search_query:
            sql += " AND (ft.description LIKE %s OR c.category_name LIKE %s)"
            like_value = f"%{search_query}%"
            values.append(like_value)
            values.append(like_value)

        sql += " ORDER BY ft.transaction_date DESC, ft.transaction_id DESC"

        cursor.execute(sql, tuple(values))
        all_transactions = cursor.fetchall()

        cursor.close()
        conn.close()

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
def edit_transaction(transaction_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        cursor.execute("SELECT * FROM categories ORDER BY category_name ASC")
        categories = cursor.fetchall()

        cursor.execute("""
            SELECT *
            FROM finance_transactions
            WHERE transaction_id = %s AND user_id = %s
        """, (transaction_id, session["user_id"]))
        transaction = cursor.fetchone()

        if not transaction:
            cursor.close()
            conn.close()
            return "Transaction not found"

        if request.method == "POST":
            category_id = request.form["category_id"]
            amount = request.form["amount"]
            transaction_type = request.form["transaction_type"]
            description = request.form["description"]
            transaction_date = request.form["transaction_date"]

            cursor.execute("""
                UPDATE finance_transactions
                SET category_id = %s,
                    amount = %s,
                    transaction_type = %s,
                    description = %s,
                    transaction_date = %s
                WHERE transaction_id = %s AND user_id = %s
            """, (
                category_id,
                amount,
                transaction_type,
                description,
                transaction_date,
                transaction_id,
                session["user_id"]
            ))
            conn.commit()

            cursor.close()
            conn.close()

            return redirect(url_for("transactions"))

        cursor.close()
        conn.close()

        return render_template(
            "edit_transaction.html",
            transaction=transaction,
            categories=categories
        )

    except Exception as e:
        return f"Error: {e}"


@app.route("/delete-transaction/<int:transaction_id>")
def delete_transaction(transaction_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(buffered=True)

        cursor.execute("""
            DELETE FROM finance_transactions
            WHERE transaction_id = %s AND user_id = %s
        """, (transaction_id, session["user_id"]))
        conn.commit()

        cursor.close()
        conn.close()

        return redirect(url_for("transactions"))

    except Exception as e:
        return f"Error: {e}"


@app.route("/time-travel", methods=["GET", "POST"])
def time_travel():
    if "user_id" not in session:
        return redirect(url_for("login"))

    balance_on_date = None
    selected_date = ""
    filtered_transactions = []

    try:
        if request.method == "POST":
            selected_date = request.form["selected_date"]

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)

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
                WHERE user_id = %s AND transaction_date <= %s
            """, (session["user_id"], selected_date))
            balance_on_date = cursor.fetchone()["balance_on_date"]

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
                WHERE ft.user_id = %s AND ft.transaction_date <= %s
                ORDER BY ft.transaction_date DESC, ft.transaction_id DESC
            """, (session["user_id"], selected_date))
            filtered_transactions = cursor.fetchall()

            cursor.close()
            conn.close()

        return render_template(
            "time_travel.html",
            balance_on_date=balance_on_date,
            selected_date=selected_date,
            filtered_transactions=filtered_transactions
        )

    except Exception as e:
        return f"Error: {e}"


@app.route("/history")
def history():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

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
            WHERE th.user_id = %s
            ORDER BY th.changed_at DESC, th.history_id DESC
        """, (session["user_id"],))
        history_records = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template("history.html", history_records=history_records)

    except Exception as e:
        return f"Error: {e}"


@app.route("/monthly-report", methods=["GET", "POST"])
def monthly_report():
    if "user_id" not in session:
        return redirect(url_for("login"))

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

            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total_income
                FROM finance_transactions
                WHERE user_id = %s
                  AND transaction_type = 'Income'
                  AND transaction_date BETWEEN %s AND %s
            """, (session["user_id"], start_date, end_date))
            total_income = cursor.fetchone()["total_income"]

            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) AS total_expense
                FROM finance_transactions
                WHERE user_id = %s
                  AND transaction_type = 'Expense'
                  AND transaction_date BETWEEN %s AND %s
            """, (session["user_id"], start_date, end_date))
            total_expense = cursor.fetchone()["total_expense"]

            savings = total_income - total_expense

            cursor.close()
            conn.close()

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
def category_report():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        cursor.execute("""
            SELECT
                c.category_name,
                COALESCE(SUM(ft.amount), 0) AS total_spent
            FROM finance_transactions ft
            JOIN categories c ON ft.category_id = c.category_id
            WHERE ft.user_id = %s
              AND ft.transaction_type = 'Expense'
            GROUP BY c.category_name
            ORDER BY total_spent DESC
        """, (session["user_id"],))
        category_data = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template("category_report.html", category_data=category_data)

    except Exception as e:
        return f"Error: {e}"


@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        user_id = session["user_id"]

        if request.method == "POST":
            monthly_budget = float(request.form["monthly_budget"])
            savings_goal = float(request.form["savings_goal"])

            if monthly_budget < 0 or savings_goal < 0:
                return "Budget and savings goal cannot be negative"

            cursor.execute("""
                UPDATE user_financial_goals
                SET monthly_budget = %s, savings_goal = %s
                WHERE user_id = %s
            """, (monthly_budget, savings_goal, user_id))

            conn.commit()
            cursor.close()
            conn.close()

            return redirect(url_for("dashboard"))

        cursor.execute("""
            SELECT monthly_budget, savings_goal
            FROM user_financial_goals
            WHERE user_id = %s
        """, (user_id,))
        goals = cursor.fetchone()

        cursor.close()
        conn.close()

        return render_template("settings.html", goals=goals)

    except Exception as e:
        return f"Error: {e}"


@app.route("/monthly-report/pdf/<selected_month>")
def monthly_report_pdf(selected_month):
    if "user_id" not in session:
        return redirect(url_for("login"))

    try:
        year, month = map(int, selected_month.split("-"))
        start_date = f"{year}-{month:02d}-01"
        last_day = calendar.monthrange(year, month)[1]
        end_date = f"{year}-{month:02d}-{last_day:02d}"

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_income
            FROM finance_transactions
            WHERE user_id = %s
              AND transaction_type = 'Income'
              AND transaction_date BETWEEN %s AND %s
        """, (session["user_id"], start_date, end_date))
        total_income = cursor.fetchone()["total_income"]

        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) AS total_expense
            FROM finance_transactions
            WHERE user_id = %s
              AND transaction_type = 'Expense'
              AND transaction_date BETWEEN %s AND %s
        """, (session["user_id"], start_date, end_date))
        total_expense = cursor.fetchone()["total_expense"]

        savings = total_income - total_expense

        cursor.close()
        conn.close()

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