# 🗄️ SQL Logic — Order Product Segment

This document explains the exact SQL queries used in the **Operations → Place Order** segment of the Inventory Management System and what each query does.

---

## 1. Loading Place Order Page
**Function:** Loads customer options, product options, and recent order activity shown in the right-side table.

### A. Load Eligible Customers
*   **File:** [main.py](main.py)
*   **Route:** `GET /create-order`

```sql
SELECT user_id, full_name, email
FROM USERS
WHERE role = 'Customer' OR role = 'Retailer';
```
*   Fetches only customers/retailers for the **Target Customer** dropdown.

### B. Load Product List
*   **File:** [main.py](main.py)
*   **Route:** `GET /create-order`

```sql
SELECT product_id, product_name, selling_price
FROM PRODUCTS;
```
*   Fills the **Asset Selection** dropdown with product IDs, names, and prices.

### C. Load Recent Order Activity
*   **File:** [main.py](main.py)
*   **Route:** `GET /create-order`

```sql
SELECT o.order_id, o.order_date, o.status,
       u.full_name AS customer_name,
       p.product_name,
       oi.quantity
FROM ORDERS o
JOIN USERS u ON o.requested_by = u.user_id
LEFT JOIN ORDER_ITEMS oi ON o.order_id = oi.order_id
LEFT JOIN PRODUCTS p ON oi.product_id = p.product_id
ORDER BY o.order_date DESC, o.order_id DESC
LIMIT 8;
```
*   Builds the recent activity table.
*   Shows latest 8 orders with customer name, product name, quantity, and status.

---

## 2. Creating a New Product Order
**Function:** Places a new order in `PENDING` state and reserves stock.

*   **File:** [main.py](main.py)
*   **Route:** `POST /create-order`

### A. Insert Order Header
```sql
INSERT INTO ORDERS (requested_by, order_date, status, order_type)
VALUES (%s, %s, %s, %s);
```
*   Creates an order row.
*   Status is set to `PENDING`.
*   `order_id` is auto-generated and reused for line items.

### B. Read Product Price
```sql
SELECT selling_price
FROM PRODUCTS
WHERE product_id = %s;
```
*   Reads current selling price to store price snapshot in line item.

### C. Insert Order Line Item
```sql
INSERT INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price)
VALUES (%s, %s, %s, %s);
```
*   Creates the product line linked to the newly created order.

### D. Reserve Inventory
```sql
UPDATE INVENTORY
SET current_stock = current_stock - %s
WHERE product_id = %s;
```
*   Reduces stock immediately for pending order reservation.

---

## 3. Decision Actions (Yes / No / Ship)
**Function:** Updates order status from Recent Order Activity and keeps inventory accurate.

*   **File:** [main.py](main.py)
*   **Route:** `POST /update-order-status`

### A. Read Current Status
```sql
SELECT status
FROM ORDERS
WHERE order_id = %s;
```
*   Checks existing status before transition logic.

### B. Update Status
```sql
UPDATE ORDERS
SET status = %s
WHERE order_id = %s;
```
*   Receives one of these values from the page actions:
    * `CONFIRMED` from **Yes**
    * `CANCELLED` from **No**
    * `SHIPPED` from **Ship**

### C. Fetch Order Items for Stock Reconciliation
```sql
SELECT product_id, quantity
FROM ORDER_ITEMS
WHERE order_id = %s;
```
*   Retrieves item quantities to reverse or re-apply stock reservation.

### D. Restore Stock on Cancel
```sql
UPDATE INVENTORY
SET current_stock = current_stock + %s
WHERE product_id = %s;
```
*   Runs when status changes from non-cancelled → `CANCELLED`.

### E. Re-Reserve Stock on Reactivation
```sql
UPDATE INVENTORY
SET current_stock = current_stock - %s
WHERE product_id = %s;
```
*   Runs when status changes from `CANCELLED` → non-cancelled.

---

## 4. Transaction Safety
For order creation and status-changing operations, the backend uses transaction control:
1. `db.commit()` on success
2. `db.rollback()` on failure

This prevents partial writes (for example, inserting an order but failing inventory update).

---

## 5. Status Flow in This Segment
1. Place Product Order → `PENDING`
2. Yes → `CONFIRMED`
3. Ship → `SHIPPED`
4. No → `CANCELLED`

This is the complete SQL-backed workflow for the screenshoted Operations place-order section.
