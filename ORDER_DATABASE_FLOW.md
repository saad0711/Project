# Operations SQL Flow

This document covers the SQL used in the Orders part of the project:
- Place Order
- Order Tracking / Management

---

## 1. Where does a new order get stored?

When someone clicks "Place Order", data goes into 3 tables:

1. **ORDERS** - the order header (who ordered, when, status)
2. **ORDER_ITEMS** - what was ordered (product, quantity, price)
3. **INVENTORY** - stock gets reduced

---

## 2. Table breakdown

| Table | What it stores | Why we need it |
|---|---|---|
| USERS | Customers and retailers | To know who placed the order |
| PRODUCTS | Product list and prices | To know what is being ordered |
| ORDERS | Order header | Main order record |
| ORDER_ITEMS | Line items | Product, quantity, price per order |
| INVENTORY | Stock levels | Track available stock |

---

## 3. Loading the Place Order page

### A. Get eligible customers

```sql
SELECT user_id, full_name, email
FROM USERS
WHERE role IN ('Customer', 'Retailer')
ORDER BY full_name ASC;
```
- Only loads users who are allowed to place orders

### B. Get products with supplier name

```sql
SELECT p.product_id, p.product_name, p.selling_price,
       COALESCE(s.full_name, 'No Supplier') AS supplier_name
FROM PRODUCTS p
LEFT JOIN USERS s ON p.supplier_id = s.user_id
ORDER BY p.product_name ASC;
```
- LEFT JOIN so products still show up even if the supplier is missing
- COALESCE gives a default label when supplier is null

### C. Get recent orders

```sql
SELECT o.order_id, o.order_date, o.status,
       u.full_name AS customer_name,
       (SELECT p2.product_name FROM ORDER_ITEMS oi2
        JOIN PRODUCTS p2 ON p2.product_id = oi2.product_id
        WHERE oi2.order_id = o.order_id
        ORDER BY oi2.item_id ASC LIMIT 1) AS product_name,
       (SELECT oi2.quantity FROM ORDER_ITEMS oi2
        WHERE oi2.order_id = o.order_id
        ORDER BY oi2.item_id ASC LIMIT 1) AS quantity,
       COALESCE((SELECT SUM(oi2.quantity * oi2.unit_price)
        FROM ORDER_ITEMS oi2 WHERE oi2.order_id = o.order_id), 0) AS total_amount,
       COALESCE((SELECT COUNT(*) FROM ORDER_ITEMS oi2
        WHERE oi2.order_id = o.order_id), 0) AS item_count
FROM ORDERS o
JOIN USERS u ON o.requested_by = u.user_id
ORDER BY o.order_date DESC, o.order_id DESC
LIMIT 8;
```
- Pulls info from ORDERS, customer name from USERS
- Subqueries get the first product name, quantity, total and item count
- One row per order

---

## 4. Creating a new order

### A. Insert order header

```sql
INSERT INTO ORDERS (requested_by, order_date, status, order_type)
VALUES (?, ?, ?, ?);
```
- New row in ORDERS with status PENDING
- order_id is auto generated

### B. Get product price

```sql
SELECT selling_price FROM PRODUCTS WHERE product_id = ?;
```
- Saves the current price so future price changes dont affect old orders

### C. Insert order item

```sql
INSERT INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price)
VALUES (?, ?, ?, ?);
```

### D. Reduce stock

```sql
UPDATE INVENTORY SET current_stock = current_stock - ? WHERE product_id = ?;
```
- Decreases stock after order is placed

---

## 5. Loading the Manage Orders page

```sql
SELECT o.order_id, o.requested_by AS customer_id,
       u.full_name AS customer_name, o.order_date, o.status,
       COALESCE((SELECT SUM(oi.quantity * oi.unit_price)
        FROM ORDER_ITEMS oi WHERE oi.order_id = o.order_id), 0) AS total_amount
FROM ORDERS o
JOIN USERS u ON o.requested_by = u.user_id
ORDER BY o.order_date DESC, o.order_id DESC;
```
- JOIN to get customer name
- Subquery to calculate order total

---

## 6. Updating order status

### A. Check current status

```sql
SELECT status FROM ORDERS WHERE order_id = ?;
```
- Need to know old status before changing it

### B. Update status

```sql
UPDATE ORDERS SET status = ? WHERE order_id = ?;
```

### C. Get order items for stock adjustment

```sql
SELECT product_id, quantity FROM ORDER_ITEMS WHERE order_id = ?;
```

### D. Give stock back when cancelling

```sql
UPDATE INVENTORY SET current_stock = current_stock + ? WHERE product_id = ?;
```

### E. Take stock back if un-cancelling

```sql
UPDATE INVENTORY SET current_stock = current_stock - ? WHERE product_id = ?;
```

---

## 7. Order status flow

1. Place Order -> PENDING
2. Approve -> CONFIRMED
3. Ship -> SHIPPED
4. Decline -> CANCELLED

The Place Order page only shows the status. The actual approve/decline buttons are on the Manage Orders page.

---

## 8. Sorting

The backend takes a `sort_by` value from the page and maps it to an ORDER BY clause. Only whitelisted sort keys are allowed so users cant inject SQL.

Example sort clauses:
```sql
-- Newest first
ORDER BY o.order_date DESC, o.order_id DESC;

-- Oldest first
ORDER BY o.order_date ASC, o.order_id ASC;

-- Highest total
ORDER BY total_amount DESC, o.order_date DESC;

-- Customer name A-Z
ORDER BY u.full_name ASC, o.order_id ASC;
```
