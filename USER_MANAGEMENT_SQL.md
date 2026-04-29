# SQL Logic - User Management

This document explains the SQL queries used in the Users section of the app.

---

## 1. Viewing and Searching Users

### A. Default View (All Users)

```sql
SELECT user_id, full_name, email, role, company_name, status, created_at
FROM USERS
ORDER BY created_at DESC;
```
- `ORDER BY created_at DESC` puts the newest users at the top

### B. Search

```sql
SELECT user_id, full_name, email, role, company_name, status, created_at
FROM USERS
WHERE full_name LIKE ?
   OR email LIKE ?
   OR role LIKE ?
   OR company_name LIKE ?
ORDER BY created_at DESC;
```
- `LIKE ?` uses wildcards like `%keyword%` to find partial matches
- `OR` lets us search across multiple columns at once

---

## 2. Adding a User

```sql
INSERT INTO USERS (full_name, email, role, company_name, status)
VALUES (?, ?, ?, ?, ?);
```
- The `?` are placeholders, this prevents SQL injection
- `user_id` is auto generated so we dont include it

---

## 3. Deleting a User

### Step 1: Check if the user has orders

```sql
SELECT order_id
FROM ORDERS
WHERE requested_by = ?
ORDER BY order_id ASC;
```
- If this returns anything, we cant delete the user because their orders would become orphaned
- We show the user which order IDs are blocking the deletion

### Step 2: Actually delete

```sql
DELETE FROM USERS
WHERE user_id = ?;
```
- Uses the unique `user_id` so we dont accidentally delete someone else

---

## Transaction Management

For add and delete, we use transactions:
1. `conn.commit()` - saves the change only if everything worked
2. `conn.rollback()` - undoes partial work if something went wrong (like a duplicate email)
