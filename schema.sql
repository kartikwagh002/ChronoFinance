CREATE DATABASE IF NOT EXISTS chronofinance;
USE chronofinance;

-- =========================
-- DROP OLD TRIGGERS
-- =========================
DROP TRIGGER IF EXISTS trg_after_transaction_insert;
DROP TRIGGER IF EXISTS trg_before_transaction_update;
DROP TRIGGER IF EXISTS trg_before_transaction_delete;

-- =========================
-- DROP OLD TABLES
-- =========================
DROP TABLE IF EXISTS transaction_history;
DROP TABLE IF EXISTS finance_transactions;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS users;

-- =========================
-- CREATE USERS TABLE
-- =========================
CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- CREATE CATEGORIES TABLE
-- =========================
CREATE TABLE categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(50) NOT NULL,
    category_type ENUM('Income', 'Expense') NOT NULL
);

-- =========================
-- CREATE MAIN TRANSACTIONS TABLE
-- =========================
CREATE TABLE finance_transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL CHECK (amount > 0),
    transaction_type ENUM('Income', 'Expense') NOT NULL,
    description VARCHAR(255),
    transaction_date DATE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_transaction_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_transaction_category
        FOREIGN KEY (category_id) REFERENCES categories(category_id)
        ON DELETE CASCADE
);

-- =========================
-- CREATE TRANSACTION HISTORY TABLE
-- =========================
CREATE TABLE transaction_history (
    history_id INT AUTO_INCREMENT PRIMARY KEY,
    transaction_id INT,
    user_id INT NOT NULL,
    category_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    transaction_type ENUM('Income', 'Expense') NOT NULL,
    description VARCHAR(255),
    transaction_date DATE NOT NULL,
    action_type ENUM('INSERT', 'UPDATE', 'DELETE') NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- =========================
-- INSERT DEFAULT CATEGORIES
-- =========================
INSERT INTO categories (category_name, category_type) VALUES
('Salary', 'Income'),
('Freelance', 'Income'),
('Bonus', 'Income'),
('Gift', 'Income'),
('Food', 'Expense'),
('Travel', 'Expense'),
('Shopping', 'Expense'),
('Bills', 'Expense'),
('Health', 'Expense'),
('Entertainment', 'Expense'),
('Rent', 'Expense'),
('Education', 'Expense');

-- =========================
-- CREATE TRIGGERS
-- =========================
DELIMITER $$

CREATE TRIGGER trg_after_transaction_insert
AFTER INSERT ON finance_transactions
FOR EACH ROW
BEGIN
    INSERT INTO transaction_history (
        transaction_id,
        user_id,
        category_id,
        amount,
        transaction_type,
        description,
        transaction_date,
        action_type
    )
    VALUES (
        NEW.transaction_id,
        NEW.user_id,
        NEW.category_id,
        NEW.amount,
        NEW.transaction_type,
        NEW.description,
        NEW.transaction_date,
        'INSERT'
    );
END$$

CREATE TRIGGER trg_before_transaction_update
BEFORE UPDATE ON finance_transactions
FOR EACH ROW
BEGIN
    INSERT INTO transaction_history (
        transaction_id,
        user_id,
        category_id,
        amount,
        transaction_type,
        description,
        transaction_date,
        action_type
    )
    VALUES (
        OLD.transaction_id,
        OLD.user_id,
        OLD.category_id,
        OLD.amount,
        OLD.transaction_type,
        OLD.description,
        OLD.transaction_date,
        'UPDATE'
    );
END$$

CREATE TRIGGER trg_before_transaction_delete
BEFORE DELETE ON finance_transactions
FOR EACH ROW
BEGIN
    INSERT INTO transaction_history (
        transaction_id,
        user_id,
        category_id,
        amount,
        transaction_type,
        description,
        transaction_date,
        action_type
    )
    VALUES (
        OLD.transaction_id,
        OLD.user_id,
        OLD.category_id,
        OLD.amount,
        OLD.transaction_type,
        OLD.description,
        OLD.transaction_date,
        'DELETE'
    );
END$$

DELIMITER ;
SHOW TABLES;
