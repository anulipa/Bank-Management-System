CREATE DATABASE bank_db;
USE bank_db;

CREATE TABLE accounts (
    account_no VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100),
    pin VARCHAR(10),
    balance DECIMAL(10,2) DEFAULT 0.00
);

CREATE TABLE transactions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    account_no VARCHAR(20),
    type VARCHAR(50),
    amount DECIMAL(10,2),
    sender_account VARCHAR(20),
    receiver_account VARCHAR(20),
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO accounts (account_no, name, pin, balance)
VALUES ('1001', 'Anu', '1234', 5000);
VALUES ('1002', 'Newton', '1234', 5000);



