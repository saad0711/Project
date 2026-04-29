-- setup_db.sql
-- Inventory Management System Database Initialization

CREATE DATABASE IF NOT EXISTS inventory_db;
USE inventory_db;

-- 1. USERS Table
CREATE TABLE IF NOT EXISTS USERS (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    role ENUM('Admin', 'Supplier', 'Customer', 'Retailer') DEFAULT 'Customer',
    company_name VARCHAR(100),
    status ENUM('Active', 'Inactive') DEFAULT 'Active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. PRODUCTS Table
CREATE TABLE IF NOT EXISTS PRODUCTS (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    category VARCHAR(50),
    unit_cost DECIMAL(10, 2) NOT NULL,
    selling_price DECIMAL(10, 2) NOT NULL,
    supplier_id INT,
    FOREIGN KEY (supplier_id) REFERENCES USERS(user_id) ON DELETE SET NULL
);

-- 3. INVENTORY Table
CREATE TABLE IF NOT EXISTS INVENTORY (
    product_id INT PRIMARY KEY,
    current_stock INT DEFAULT 0,
    min_threshold INT DEFAULT 10,
    last_restock_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id) ON DELETE CASCADE
);

-- 4. ORDERS Table
CREATE TABLE IF NOT EXISTS ORDERS (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    requested_by INT NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status ENUM('PENDING', 'CONFIRMED', 'SHIPPED', 'DELIVERED', 'CANCELLED') DEFAULT 'PENDING',
    order_type VARCHAR(20),
    FOREIGN KEY (requested_by) REFERENCES USERS(user_id)
);

-- Ensure existing MySQL databases also support CONFIRMED status.
ALTER TABLE ORDERS
MODIFY COLUMN status ENUM('PENDING', 'CONFIRMED', 'SHIPPED', 'DELIVERED', 'CANCELLED') DEFAULT 'PENDING';

-- 5. ORDER_ITEMS Table
CREATE TABLE IF NOT EXISTS ORDER_ITEMS (
    item_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10, 2) NOT NULL,
    FOREIGN KEY (order_id) REFERENCES ORDERS(order_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id)
);

-- ==========================================
-- 6. OPERATIONS-ONLY SQL ENHANCEMENTS
-- ==========================================
-- These objects make order placement and tracking cleaner, faster, and more presentable.

CREATE INDEX idx_orders_customer_status_date
ON ORDERS (requested_by, status, order_date);

CREATE INDEX idx_orders_date_id
ON ORDERS (order_date, order_id);

CREATE INDEX idx_order_items_order_product
ON ORDER_ITEMS (order_id, product_id);

CREATE INDEX idx_order_items_product_order
ON ORDER_ITEMS (product_id, order_id);

CREATE OR REPLACE VIEW ORDER_ACTIVITY_OVERVIEW AS
SELECT
    o.order_id,
    o.order_date,
    o.status,
    o.order_type,
    u.user_id AS customer_id,
    u.full_name AS customer_name,
    COALESCE(summary.total_amount, 0) AS total_amount,
    COALESCE(summary.item_count, 0) AS item_count,
    (
        SELECT p.product_name
        FROM ORDER_ITEMS oi
        JOIN PRODUCTS p ON p.product_id = oi.product_id
        WHERE oi.order_id = o.order_id
        ORDER BY oi.item_id ASC
        LIMIT 1
    ) AS first_product_name,
    (
        SELECT oi.quantity
        FROM ORDER_ITEMS oi
        WHERE oi.order_id = o.order_id
        ORDER BY oi.item_id ASC
        LIMIT 1
    ) AS first_quantity
FROM ORDERS o
JOIN USERS u ON u.user_id = o.requested_by
LEFT JOIN (
    SELECT
        order_id,
        SUM(quantity * unit_price) AS total_amount,
        COUNT(*) AS item_count
    FROM ORDER_ITEMS
    GROUP BY order_id
) summary ON summary.order_id = o.order_id;

CREATE OR REPLACE VIEW ORDER_ITEM_LINES AS
SELECT
    o.order_id,
    o.order_date,
    o.status,
    u.full_name AS customer_name,
    p.product_name,
    p.category,
    oi.quantity,
    oi.unit_price,
    (oi.quantity * oi.unit_price) AS line_total
FROM ORDERS o
JOIN USERS u ON u.user_id = o.requested_by
JOIN ORDER_ITEMS oi ON oi.order_id = o.order_id
JOIN PRODUCTS p ON p.product_id = oi.product_id;

-- ==========================================
-- SEED DATA (BEAUTIFUL PLACEHOLDERS)
-- ==========================================

-- Insert Users
INSERT INTO USERS (full_name, email, role, company_name, status) VALUES
('Ahnaf Zakaria', 'ahnaf@example.com', 'Admin', 'IMS Core Teams', 'Active'),
('Global Tech Logistics', 'contact@gtl.com', 'Supplier', 'GTL Corp', 'Active'),
('Nexus Synergy', 'sales@nexus.com', 'Supplier', 'Nexus Synergy', 'Active'),
('Jane Doe', 'jane.doe@retail.com', 'Retailer', 'Jane\'s Boutique', 'Active'),
('John Smith', 'john@gmail.com', 'Customer', NULL, 'Active');

-- Insert Products
INSERT INTO PRODUCTS (product_name, category, unit_cost, selling_price, supplier_id) VALUES
('Quantum Processor V1', 'Electronics', 150.00, 299.99, 2),
('Cybernetic Lens', 'Optics', 45.50, 89.00, 2),
('Aero-Draft Keyboard', 'Peripherals', 30.00, 75.00, 3),
('Bio-Sync Smartwatch', 'Wearables', 80.00, 159.99, 3),
('Titanium Chassis M1', 'Hardware', 200.00, 450.00, 2);

-- Insert Inventory
INSERT INTO INVENTORY (product_id, current_stock, min_threshold) VALUES
(1, 15, 5),
(2, 4, 10), -- Low Stock
(3, 50, 15),
(4, 2, 5),  -- Low Stock
(5, 12, 3);

-- Insert Some Initial Orders
INSERT INTO ORDERS (requested_by, status, order_type) VALUES
(4, 'DELIVERED', 'retail'),
(4, 'PENDING', 'retail'),
(5, 'PENDING', 'personal');

-- Insert Order Items
INSERT INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 2, 299.99),
(1, 3, 1, 75.00),
(2, 2, 5, 89.00),
(3, 4, 1, 159.99);
