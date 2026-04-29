-- setup_db.sql
-- Creates all tables and inserts sample data for the Inventory Management System
-- This is the MySQL version, the app also works with SQLite (see database.py)

CREATE DATABASE IF NOT EXISTS inventory_db;
USE inventory_db;

-- Users table, stores admins, suppliers, customers and retailers
CREATE TABLE IF NOT EXISTS USERS (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    role ENUM('Admin', 'Supplier', 'Customer', 'Retailer') DEFAULT 'Customer',
    company_name VARCHAR(100),
    status ENUM('Active', 'Inactive') DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Products table
CREATE TABLE IF NOT EXISTS PRODUCTS (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    unit_cost DECIMAL(10, 2) NOT NULL,
    selling_price DECIMAL(10, 2) NOT NULL,
    supplier_id INT,
    FOREIGN KEY (supplier_id) REFERENCES USERS(user_id) ON DELETE SET NULL
);

-- Inventory tracks stock levels for each product
CREATE TABLE IF NOT EXISTS INVENTORY (
    product_id INT PRIMARY KEY,
    current_stock INT DEFAULT 0,
    min_threshold INT DEFAULT 10,
    last_restock_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id) ON DELETE CASCADE
);

-- Orders table
CREATE TABLE IF NOT EXISTS ORDERS (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    requested_by INT NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('PENDING', 'CONFIRMED', 'SHIPPED', 'DELIVERED', 'CANCELLED') DEFAULT 'PENDING',
    order_type VARCHAR(20),
    FOREIGN KEY (requested_by) REFERENCES USERS(user_id)
);

-- Each row here is one item inside an order
CREATE TABLE IF NOT EXISTS ORDER_ITEMS (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES ORDERS(order_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id)
);

-- Sample data

INSERT INTO USERS (full_name, email, role, company_name, status) VALUES
('Ahnaf Zakaria', 'ahnaf@example.com', 'Admin', 'IMS Core Teams', 'Active'),
('Global Tech Logistics', 'contact@gtl.com', 'Supplier', 'GTL Corp', 'Active'),
('Nexus Synergy', 'sales@nexus.com', 'Supplier', 'Nexus Synergy', 'Active'),
('Jane Doe', 'jane.doe@retail.com', 'Retailer', 'Jane\'s Boutique', 'Active'),
('John Smith', 'john@gmail.com', 'Customer', NULL, 'Active');

INSERT INTO PRODUCTS (product_name, category, unit_cost, selling_price, supplier_id) VALUES
('Quantum Processor V1', 'Electronics', 150.00, 299.99, 2),
('Cybernetic Lens', 'Optics', 45.50, 89.00, 2),
('Aero-Draft Keyboard', 'Peripherals', 30.00, 75.00, 3),
('Bio-Sync Smartwatch', 'Wearables', 80.00, 159.99, 3),
('Titanium Chassis M1', 'Hardware', 200.00, 450.00, 2);

INSERT INTO INVENTORY (product_id, current_stock, min_threshold) VALUES
(1, 15, 5),
(2, 4, 10),
(3, 50, 15),
(4, 2, 5),
(5, 12, 3);

INSERT INTO ORDERS (requested_by, status, order_type) VALUES
(4, 'DELIVERED', 'retail'),
(4, 'PENDING', 'retail'),
(5, 'PENDING', 'personal');

INSERT INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 2, 299.99),
(1, 3, 1, 75.00),
(2, 2, 5, 89.00),
(3, 4, 1, 159.99);
