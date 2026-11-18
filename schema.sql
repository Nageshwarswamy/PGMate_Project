CREATE DATABASE IF NOT EXISTS pgmate;
USE pgmate;

CREATE TABLE IF NOT EXISTS residents (
    resident_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    room_number VARCHAR(20) NOT NULL,
    joining_date DATE NOT NULL,
    leaving_date DATE NULL,
    monthly_rent DECIMAL(10,2) NOT NULL DEFAULT 0,
    security_deposit DECIMAL(10,2) NOT NULL DEFAULT 0,
    maintenance_fee DECIMAL(10,2) NOT NULL DEFAULT 0,
    advance_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
    notice_date DATE NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rent_payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    resident_id INT NOT NULL,
    rent_month VARCHAR(30) NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    payment_date DATE NOT NULL,
    status ENUM('Paid','Pending') NOT NULL DEFAULT 'Paid',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (resident_id) REFERENCES residents(resident_id) ON DELETE CASCADE
);

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
);

CREATE TABLE IF NOT EXISTS pg_settings (
    setting_key VARCHAR(80) PRIMARY KEY,
    setting_value VARCHAR(255) NOT NULL DEFAULT ''
);

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
);

INSERT IGNORE INTO pg_settings(setting_key,setting_value)
VALUES ('pg_name','PGMate'),('upi_id','');
