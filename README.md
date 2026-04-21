# 💰 ChronoFinance

ChronoFinance is a **DBMS-based financial tracking web application** built using Flask and SQLite.
It allows users to manage income, expenses, and financial goals with advanced features like **transaction history tracking, time travel queries, and PDF report generation**.

---

## 🚀 Live Demo

🌐 https://chronofinance.onrender.com/  
🌐 https://chronofinance-1.onrender.com/

*(Note: This is a demo deployment. Data may reset due to free hosting limitations.)*

---

## 📌 Features

* 🔐 User Authentication (Register/Login)
* 💵 Add, Edit, Delete Transactions
* 📊 Dashboard with Financial Summary
* 📅 Monthly Reports (Income, Expense, Savings)
* 📄 PDF Report Download with Footer
* 🕒 Time Travel Query (View past financial state)
* 🧾 Transaction History Tracking (INSERT/UPDATE/DELETE logs)
* 🎯 Budget & Savings Goals Management
* 🔎 Search & Filter Transactions
* 📈 Category-wise Analysis

---

## 🛠️ Tech Stack

* **Backend:** Python (Flask)
* **Database:** SQLite (DBMS)
* **Frontend:** HTML, CSS, Bootstrap
* **PDF Generation:** FPDF
* **Deployment:** Render

---

## 🗄️ Database Design

### Tables Used:

* `users`
* `categories`
* `finance_transactions`
* `transaction_history`
* `user_financial_goals`

### DBMS Concepts Used:

* Primary Keys & Foreign Keys
* One-to-Many Relationships
* Data Integrity Constraints
* Transaction Logging
* Normalization

---

## ⚙️ Installation & Setup (Local)

1. Clone the repository:

```bash
git clone https://github.com/kartikwagh002/ChronoFinance.git
cd ChronoFinance
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Initialize database:

```bash
python init_db.py
```

4. Run the application:

```bash
python app.py
```

5. Open in browser:

```

```

---

## 📷 Screenshots

Opening Interface  -  ![alt text](image-1.png)
Account Creation   -  ![alt text](image-2.png)
Login Page         -  ![alt text](image-3.png)
Dashboard          -  ![alt text](image-4.png)
                      ![alt text](image-5.png)
                      ![alt text](image-6.png)
Add Transaction    -  ![alt text](image-7.png)
All Transactions   -  ![alt text](image-8.png)
History Page       -  ![alt text](image-9.png)
Monthly Report     -  ![alt text](image-10.png)
Financial Settings -  ![alt text](image-11.png)


## ⚠️ Important Note

This project is developed for **DBMS academic purposes**.
SQLite is used as the database, and due to free hosting limitations on Render, data may not persist permanently.

---

## 🚀 Future Enhancements

* PostgreSQL/MySQL integration for production
* Advanced analytics dashboards
* Mobile responsiveness improvements
* Cloud database support

---

## 👨‍💻 Author

**Kartik Wagh**
Second Year AIML Engineering Student

---

## ⭐ Project Objective

To demonstrate practical implementation of **Database Management System concepts** including relational schema design, data integrity, and transaction tracking.

---

## 📌 License

This project is for educational purposes only.
