# 🗄️ SQL Logic — Manage Users Segment

This document explains the exact SQL queries used in the **Manage Users** segment of the Inventory Management System and how they handle each core function.

---

## 1. Viewing & Searching Users
**Function:** Fetches the list of all users to display in the management table. Handles both the default view and filtered search results.

### A. Default View (All Users)
When you first open the page, this query runs to show everyone, starting with the newest members.
```sql
SELECT user_id, full_name, email, role, company_name, status, created_at
FROM USERS
ORDER BY created_at DESC;
```
*   **`ORDER BY created_at DESC`**: Ensures that the most recently added users appear at the top for immediate verification.

### B. Filtered Search
If you type something into the search bar, the query changes to look for matches across multiple columns.
```sql
SELECT user_id, full_name, email, role, company_name, status, created_at
FROM USERS
WHERE full_name LIKE %s
   OR email LIKE %s
   OR role LIKE %s
   OR company_name LIKE %s
ORDER BY created_at DESC;
```
*   **`LIKE %s`**: Uses wildcards (e.g., `%keyword%`) to find partial matches. If you search for "Ahnaf", it will find "Ahnaf Zakaria".
*   **`OR`**: Allows the system to find the term regardless of whether it's a name, email, or company.

---

## 2. Adding a New User
**Function:** Creates a persistent record for a new member in the system.

```sql
INSERT INTO USERS (full_name, email, role, company_name, status) 
VALUES (%s, %s, %s, %s, %s);
```
*   **Columns**: Specifies where the data goes (`full_name`, `email`, etc.).
*   **`VALUES`**: The `%s` are placeholders. This prevents **SQL Injection** by making sure the database treats the input as "data" only, not as "code".
*   **Auto-ID**: Note that `user_id` is not in this query; the database generates it automatically using `AUTO_INCREMENT`.

---

## 3. Removing a User (With Safety Checks)
**Function:** Safely removes a user while ensuring "Referential Integrity" (no ghost users linked to active orders).

### Step 1: The Dependency Check
Before deleting, the system checks if the user is "requested_by" in any existing orders.
```sql
SELECT order_id 
FROM ORDERS 
WHERE requested_by = %s 
ORDER BY order_id ASC;
```
*   **Logic**: If this returns even one `order_id`, the system cancels the deletion and shows you exactly which orders are blocking it.

### Step 2: The Deletion
If no orders are found, the system proceeds with the actual removal.
```sql
DELETE FROM USERS 
WHERE user_id = %s;
```
*   **`WHERE user_id = %s`**: This is critical. It targets the unique ID to ensure we don't accidentally delete multiple people with the same name.

---

## 🛡️ Important: Transaction Management
For **Add** and **Delete** actions, the system uses **Transactions**:
1.  **`db.commit()`**: Only if the SQL command finishes perfectly does the database "save" the change.
2.  **`db.rollback()`**: If there is an error (like a duplicate email or a server crash mid-way), the system "undoes" the partial work so the data stays perfect.

---

*This SQL structure follows standard relational database principles common in CSE 370 and industry-grade systems.* 🚀
