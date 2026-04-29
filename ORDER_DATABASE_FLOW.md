# Operations Database Flow

This document explains only the **Operations** part of the project:
- **Place Order**
- **Order Tracking**

---

## 1. Direct answer: where is a new order stored?
When a user clicks **Place Product Order**, the order is stored in the database in this order:

1. **ORDERS** table
   - Stores the main order header
   - Example fields: `order_id`, `requested_by`, `order_date`, `status`, `order_type`

2. **ORDER_ITEMS** table
   - Stores the product inside that order
   - Example fields: `order_id`, `product_id`, `quantity`, `unit_price`

3. **INVENTORY** table
   - Updates stock after the order is created
   - Reduces stock for a placed order
   - Restores stock when an order is cancelled

So the final answer is:
- **ORDERS** stores the order itself
- **ORDER_ITEMS** stores what was ordered
- **INVENTORY** stores the stock effect of that order

---

## 2. Table role map
| Table | What it stores | Why it is used |
|---|---|---|
| `USERS` | Customers and retailers | To know who placed the order |
| `PRODUCTS` | Product list and prices | To know what is being ordered |
| `ORDERS` | Order header | Stores the main order record |
| `ORDER_ITEMS` | Order line items | Stores the product, quantity, and unit price |
| `INVENTORY` | Stock levels | Keeps track of current available stock |

---

## 3. Place Order page loading SQL
**File:** `main.py`  
**Route:** `GET /create-order`

### A. Load eligible customers
```sql
SELECT u.user_id, u.full_name, u.email
FROM USERS u
WHERE u.role IN ('Customer', 'Retailer')
ORDER BY u.full_name ASC;
```
**Why this is used:**
- Loads only the users allowed to place an order.
- Uses `IN (...)` to keep the condition clean.

### B. Load products with supplier info
```sql
SELECT p.product_id, p.product_name, p.selling_price,
       COALESCE(s.full_name, 'No Supplier') AS supplier_name
FROM PRODUCTS p
LEFT JOIN USERS s ON p.supplier_id = s.user_id
ORDER BY p.product_name ASC;
```
**Why this is used:**
- Shows the product list for order placement.
- Uses `LEFT JOIN` so products still appear even if supplier is missing.
- Uses `COALESCE` to show a default label when supplier name is null.

### C. Load recent order activity
```sql
SELECT
    o.order_id,
    o.order_date,
    o.status,
    u.full_name AS customer_name,
    (
        SELECT p2.product_name
        FROM ORDER_ITEMS oi2
        JOIN PRODUCTS p2 ON p2.product_id = oi2.product_id
        WHERE oi2.order_id = o.order_id
        ORDER BY oi2.item_id ASC
        LIMIT 1
    ) AS product_name,
    (
        SELECT oi2.quantity
        FROM ORDER_ITEMS oi2
        WHERE oi2.order_id = o.order_id
        ORDER BY oi2.item_id ASC
        LIMIT 1
    ) AS quantity,
    COALESCE((
        SELECT SUM(oi2.quantity * oi2.unit_price)
        FROM ORDER_ITEMS oi2
        WHERE oi2.order_id = o.order_id
    ), 0) AS total_amount,
    COALESCE((
        SELECT COUNT(*)
        FROM ORDER_ITEMS oi2
        WHERE oi2.order_id = o.order_id
    ), 0) AS item_count
FROM ORDERS o
JOIN USERS u ON o.requested_by = u.user_id
ORDER BY o.order_date DESC, o.order_id DESC
LIMIT 8;
```
**What this does:**
- Pulls order info from `ORDERS`
- Pulls customer name from `USERS`
- Pulls item/product details using nested queries from `ORDER_ITEMS` and `PRODUCTS`
- Gives one clear row per order
- Shows `total_amount` and `item_count` using subqueries

---

## 4. Creating a new order
**File:** `main.py`  
**Route:** `POST /create-order`

### A. Insert the order header
```sql
INSERT INTO ORDERS (requested_by, order_date, status, order_type)
VALUES (%s, %s, %s, %s);
```
**What happens here:**
- A new row is created in `ORDERS`
- The order starts with status `PENDING`
- This is the first place where the order is stored
- `order_id` is generated automatically

### B. Read product price
```sql
SELECT selling_price
FROM PRODUCTS
WHERE product_id = %s;
```
**What this does:**
- Fetches the current selling price
- This price is saved inside the order item so future price changes do not affect old orders

### C. Insert order item
```sql
INSERT INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price)
VALUES (%s, %s, %s, %s);
```
**What this does:**
- Stores the ordered product under the order header
- Connects the item to `order_id`

### D. Reserve inventory
```sql
UPDATE INVENTORY
SET current_stock = current_stock - %s
WHERE product_id = %s;
```
**What this does:**
- Decreases stock after order creation
- Prevents over-selling
- This is the inventory effect of placing the order

---

## 5. Order Tracking SQL
**File:** `main.py`  
**Route:** `GET /manage-orders`

### A. Order tracking query
```sql
SELECT
    o.order_id,
    o.requested_by AS customer_id,
    u.full_name AS customer_name,
    o.order_date,
    o.status,
    COALESCE((
        SELECT SUM(oi.quantity * oi.unit_price)
        FROM ORDER_ITEMS oi
        WHERE oi.order_id = o.order_id
    ), 0) AS total_amount
FROM ORDERS o
JOIN USERS u ON o.requested_by = u.user_id
ORDER BY o.order_date DESC, o.order_id DESC;
```
**Why this is used:**
- Shows all orders in the tracking page
- Uses `JOIN` to get customer name from `USERS`
- Uses a nested query to calculate the order total from `ORDER_ITEMS`
- Gives one clean row per order

---

## 6. Updating order status
**File:** `main.py`  
**Route:** `POST /update-order-status`

### A. Check current status
```sql
SELECT status
FROM ORDERS
WHERE order_id = %s;
```
**Why this is used:**
- Reads the old status before changing it
- Helps decide whether inventory must be restored or reserved again

### B. Update order status
```sql
UPDATE ORDERS
SET status = %s
WHERE order_id = %s;
```
**What this does:**
- Updates the order to `CONFIRMED`, `CANCELLED`, or `SHIPPED`
- This update happens from the Order Tracking page

### C. Fetch order items for inventory correction
```sql
SELECT product_id, quantity
FROM ORDER_ITEMS
WHERE order_id = %s;
```
**Why this is used:**
- Gets the products and quantities attached to the order
- Needed for stock adjustment

### D. Restore stock when cancelling
```sql
UPDATE INVENTORY
SET current_stock = current_stock + %s
WHERE product_id = %s;
```
**What this does:**
- Returns stock back to inventory if the order is cancelled

### E. Re-reserve stock if cancelled order becomes active again
```sql
UPDATE INVENTORY
SET current_stock = current_stock - %s
WHERE product_id = %s;
```
**What this does:**
- Decreases stock again if the order is reactivated from `CANCELLED`

---

## 7. Status flow in Operations
1. **Place Product Order** → `PENDING`
2. **Yes** in Order Tracking → `CONFIRMED`
3. **Ship** in Order Tracking → `SHIPPED`
4. **No** in Order Tracking → `CANCELLED`

**Important point:**
- The **Place Order** page only shows the current decision/result.
- The actual decision buttons are in **Order Tracking**.

---

## 8. Why these SQL queries look more advanced
These queries are a little more polished because they use:
- `JOIN` to connect related tables
- `LEFT JOIN` to keep product rows even when supplier data is missing
- Nested subqueries to calculate totals and pick item details
- `COALESCE` to avoid null values
- `ORDER BY` and `LIMIT` to show the most recent records first

---

## 9. Short conclusion
The order is first stored in **ORDERS**, then its items go into **ORDER_ITEMS**, and finally **INVENTORY** is updated. That is the full database flow for the Operations part of the project.

---

## 10. Sorting feature in Operations
**Purpose:** Lets the user sort the recent orders on the Place Order page and the full list on the Order Tracking page.

### Sort key handling
The backend accepts a `sort_by` value from the page and maps it to a safe SQL `ORDER BY` clause. Only approved sort keys are allowed.

### Example sort options
```sql
-- Newest first
ORDER BY o.order_date DESC, o.order_id DESC;

-- Oldest first
ORDER BY o.order_date ASC, o.order_id ASC;

-- Highest total amount first
ORDER BY total_amount DESC, o.order_date DESC, o.order_id DESC;

-- Customer name A-Z
ORDER BY u.full_name ASC, o.order_id ASC;
```

### Why the code is a little fancy
- Uses `WITH` CTEs to summarize order totals and item counts
- Uses nested subqueries to pick the first item in an order for display
- Uses `JOIN` and `LEFT JOIN` to keep the query readable and connected across tables
- Uses a whitelist so the sort value is safe and predictable
