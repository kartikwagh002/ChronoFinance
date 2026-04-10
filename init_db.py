import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "chronofinance.db")


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        category_id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_name TEXT NOT NULL UNIQUE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS finance_transactions (
        transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        transaction_type TEXT NOT NULL,
        amount REAL NOT NULL,
        description TEXT,
        transaction_date TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (category_id) REFERENCES categories(category_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transaction_history (
        history_id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER,
        user_id INTEGER NOT NULL,
        category_id INTEGER,
        transaction_type TEXT NOT NULL,
        amount REAL NOT NULL,
        description TEXT,
        transaction_date TEXT NOT NULL,
        action_type TEXT NOT NULL,
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(user_id),
        FOREIGN KEY (category_id) REFERENCES categories(category_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS user_financial_goals (
        goal_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        monthly_budget REAL DEFAULT 10000,
        savings_goal REAL DEFAULT 50000,
        FOREIGN KEY (user_id) REFERENCES users(user_id)
    )
    """)

    default_categories = [
        "Salary", "Freelance", "Food", "Travel", "Shopping",
        "Bills", "Health", "Entertainment", "Education", "Other"
    ]

    for category in default_categories:
        cursor.execute("""
            INSERT OR IGNORE INTO categories (category_name)
            VALUES (?)
        """, (category,))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database and tables created successfully.")
    