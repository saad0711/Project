# Inventory Management System - Core Architecture & SQL Reference

This document serves as a comprehensive study guide for your viva, detailing the application's technology stack, relational architecture, and the raw SQL queries that power the Core segments.

---

## 1. General Tech Stack

*   **Backend Framework**: **Python 3** with **FastAPI** (High-performance, async-capable web framework).
*   **Web Server**: **Uvicorn** (ASGI server used to run the FastAPI application).
*   **Database Engine**: **SQLite3** (A zero-configuration, file-based relational database).
*   **Database Access Method**: **Raw SQL Queries** via Python's standard `sqlite3` library. (No ORMs like SQLAlchemy were used, demonstrating direct control over SQL syntax and performance).
*   **Frontend**: **HTML5, CSS3, Bootstrap 5** (For responsive grids, beautiful styling, and modals), and **Jinja2** (For server-side HTML template rendering and variable injection).

---

## 2. Entity Relationships & System Connections

### How Users and Suppliers are Connected (Extension Pattern)
In this system, a Supplier is not a completely isolated entity; a Supplier **is** a User.
*   **The Connection**: The `USERS` table stores the core identity (Email, Full Name, Password, Role). The `SUPPLIERS` table acts as an "extension" to the Users table. It holds a Foreign Key (`user_id`) that links directly back to the `USERS` table.
*   **Database Constraint**: `FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE`. This ensures that if the core User profile is hard-deleted, the associated Supplier profile is automatically wiped out by the database to prevent orphaned records.

### How the "Core" Segment connects to the "Orders" Segment
The Order lifecycle directly manipulates Core tables (Users, Products, and Inventory).
1.  **Identity Link**: The `ORDERS` table tracks who placed the order via `ORDERS.requested_by`, which is a Foreign Key linking to `USERS.user_id`.
2.  **Product Link**: The `ORDER_ITEMS` table bridges orders to the physical items. It contains `product_id`, linking directly back to the `PRODUCTS` table.
3.  **Inventory Impact**: The most critical connection occurs during order placement. When a user submits an order, the backend executes an `INSERT` into the `ORDERS` table, and simultaneously executes an `UPDATE` on the `INVENTORY` table to instantly deduct `current_stock`.

---

## 3. Core SQL Queries (Tabular Reference)

Here are the most important, feature-defining SQL queries powering the Core segment, formatted for easy study.

| Core Feature / Functionality | SQL Query Used in Codebase | Purpose & Explanation |
| :--- | :--- | :--- |
| **Dashboard: Global Metrics** | `SELECT COUNT(*) FROM USERS WHERE status != 'Deleted'` | Fetches the total number of active users for the top dashboard overview cards, explicitly ignoring soft-deleted users. |
| **Dashboard: Top Selling Products** | `SELECT p.product_name, SUM(oi.quantity) as total_sold FROM ORDER_ITEMS oi JOIN PRODUCTS p ON oi.product_id = p.product_id JOIN ORDERS o ON oi.order_id = o.order_id WHERE o.archived = 0 GROUP BY p.product_id ORDER BY total_sold DESC LIMIT 5` | Uses complex **table JOINS** across `ORDER_ITEMS`, `PRODUCTS`, and `ORDERS` to calculate the best-selling products by aggregating historical quantities. |
| **Users: Search & List** | `SELECT u.*, (SELECT COUNT(*) FROM ORDERS o WHERE o.requested_by = u.user_id AND o.archived = 0) AS order_count FROM USERS u WHERE u.full_name LIKE ? AND u.status != 'Deleted'` | Uses a **Nested Subquery** to dynamically attach the active order count directly to the user row, while using `LIKE ?` for search functionality. |
| **Users: Soft Deletion Safety** | `UPDATE USERS SET status = 'Deleted' WHERE user_id = ?` | If a user has historical (archived) orders, we soft-delete them by changing their status. This prevents SQL Foreign Key constraint crashes and preserves historical revenue data. |
| **Suppliers: Identify Unregistered Users** | `SELECT u.user_id, u.full_name FROM USERS u LEFT JOIN SUPPLIERS s ON u.user_id = s.user_id WHERE s.supplier_id IS NULL AND u.status != 'Deleted'` | Uses a **LEFT JOIN** to find users who do *not* currently have a corresponding record in the SUPPLIERS table (used to populate the "Add Supplier" dropdown). |
| **Suppliers: Block Unsafe Deletion** | `SELECT COUNT(*) FROM ORDER_ITEMS oi JOIN ORDERS o ON oi.order_id = o.order_id JOIN PRODUCTS p ON oi.product_id = p.product_id WHERE p.supplier_id = ? AND o.status = 'PENDING'` | A defensive query that checks if any products belonging to a supplier are currently tied to an active, pending order before allowing the supplier to be deleted. |
| **Products: Supplier Catalog** | `SELECT p.product_name, p.selling_price, i.current_stock FROM PRODUCTS p LEFT JOIN INVENTORY i ON p.product_id = i.product_id WHERE p.supplier_id = ?` | Fetches a specific supplier's products and uses a **LEFT JOIN** on the `INVENTORY` table to seamlessly display live stock numbers on their personal dashboard. |
| **Products: Add Product Execution** | `INSERT INTO PRODUCTS (product_name, category, unit_cost, selling_price, supplier_id) VALUES (?, ?, ?, ?, ?)` | Inserts the base product details. In the Python code, this is immediately followed by grabbing `cursor.lastrowid` to securely populate the subsequent `INVENTORY` table insert. |
| **Inventory: Live Stock Deduction** | `UPDATE INVENTORY SET current_stock = current_stock - ? WHERE product_id = ?` | Executed when a user places an order. Dynamically and securely deducts the requested quantity from the current physical stock in a single transaction. |
