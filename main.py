from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
import database
from datetime import datetime
from urllib.parse import quote_plus

app = FastAPI(title="Inventory Management System")
app.add_middleware(SessionMiddleware, secret_key="ims-secret-key-370")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


## sorting options for orders pages
SORT_OPTIONS = [
    {"value": "newest", "label": "Newest First"},
    {"value": "oldest", "label": "Oldest First"},
    {"value": "highest_total", "label": "Highest Total"},
    {"value": "lowest_total", "label": "Lowest Total"},
    {"value": "customer_az", "label": "Customer A-Z"},
    {"value": "customer_za", "label": "Customer Z-A"},
    {"value": "status", "label": "Status"},
    {"value": "most_items", "label": "Most Items"},
]

SORT_SQL = {
    "newest": "o.order_date DESC, o.order_id DESC",
    "oldest": "o.order_date ASC, o.order_id ASC",
    "highest_total": "total_amount DESC, o.order_date DESC",
    "lowest_total": "total_amount ASC, o.order_date ASC",
    "customer_az": "u.full_name ASC, o.order_id ASC",
    "customer_za": "u.full_name DESC, o.order_id DESC",
    "status": "o.status ASC, o.order_date DESC",
    "most_items": "item_count DESC, o.order_date DESC",
}


def clean_sort(sort_by):
    s = (sort_by or "newest").strip().lower()
    if s in SORT_SQL:
        return s
    return "newest"


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def get_session_user(request):
    ## pulls logged in user info from the session cookie
    ## returns None if not logged in
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return {
        "user_id": user_id,
        "full_name": request.session.get("full_name"),
        "email": request.session.get("email"),
        "role": request.session.get("role"),
    }


def require_login(request):
    ## returns redirect to login if not logged in, None if ok
    if not get_session_user(request):
        return RedirectResponse(url="/login", status_code=303)
    return None


def require_admin(request):
    ## returns redirect if not admin, None if ok
    user = get_session_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=303)
    if user["role"] != "Admin":
        return RedirectResponse(url="/user-dashboard", status_code=303)
    return None


# ---------- LOGIN / REGISTER / LOGOUT ----------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    ## if already logged in, send to the right dashboard
    user = get_session_user(request)
    if user:
        if user["role"] == "Admin":
            return RedirectResponse(url="/dashboard", status_code=303)
        return RedirectResponse(url="/user-dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")
    return templates.TemplateResponse(request=request, name="login.html", context={
        "error": error, "success": success,
    })


@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "").strip()

    if not email or not password:
        return RedirectResponse(url="/login?error=Please+fill+all+fields", status_code=303)

    conn = database.get_connection()
    if conn is None:
        return RedirectResponse(url="/login?error=Database+error", status_code=303)

    cursor = conn.cursor()
    try:
        hashed = database.hash_password(password)
        cursor.execute(
            "SELECT user_id, full_name, email, role FROM USERS "
            "WHERE email = ? AND password = ? AND status = 'Active'",
            (email, hashed)
        )
        user = cursor.fetchone()

        if not user:
            return RedirectResponse(url="/login?error=Invalid+email+or+password", status_code=303)

        ## save user info in session
        request.session["user_id"] = user["user_id"]
        request.session["full_name"] = user["full_name"]
        request.session["email"] = user["email"]
        request.session["role"] = user["role"]

        ## send to the right dashboard based on role
        if user["role"] == "Admin":
            return RedirectResponse(url="/dashboard", status_code=303)
        return RedirectResponse(url="/user-dashboard", status_code=303)

    except Exception as e:
        print(f"Login error: {e}")
        return RedirectResponse(url="/login?error=Something+went+wrong", status_code=303)
    finally:
        cursor.close()
        conn.close()


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    error = request.query_params.get("error", "")
    return templates.TemplateResponse(request=request, name="register.html", context={
        "error": error,
    })


@app.post("/register")
async def register_submit(request: Request):
    form = await request.form()
    full_name = form.get("full_name", "").strip()
    email = form.get("email", "").strip().lower()
    password = form.get("password", "").strip()
    role = form.get("role", "User").strip()
    company_name = form.get("company_name", "").strip()

    if not full_name or not email or not password:
        return RedirectResponse(url="/register?error=Please+fill+all+required+fields", status_code=303)

    if role not in ("Admin", "User"):
        role = "User"

    conn = database.get_connection()
    if conn is None:
        return RedirectResponse(url="/register?error=Database+error", status_code=303)

    cursor = conn.cursor()
    try:
        hashed = database.hash_password(password)
        cursor.execute(
            "INSERT INTO USERS (full_name, email, password, role, company_name, status) "
            "VALUES (?, ?, ?, ?, ?, 'Active')",
            (full_name, email, hashed, role, company_name or None)
        )
        conn.commit()
        msg = quote_plus("Account created! You can now log in.")
        return RedirectResponse(url=f"/login?success={msg}", status_code=303)
    except Exception as e:
        print(f"Register error: {e}")
        conn.rollback()
        return RedirectResponse(url="/register?error=Email+already+taken+or+invalid+input", status_code=303)
    finally:
        cursor.close()
        conn.close()


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ---------- USER DASHBOARD ----------

@app.get("/user-dashboard", response_class=HTMLResponse)
async def user_dashboard(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        ## get this users orders
        cursor.execute(
            "SELECT o.order_id, o.order_date, o.status, "
            "COALESCE((SELECT SUM(oi.quantity * oi.unit_price) "
            " FROM ORDER_ITEMS oi WHERE oi.order_id = o.order_id), 0) AS total_amount "
            "FROM ORDERS o WHERE o.requested_by = ? "
            "ORDER BY o.order_date DESC LIMIT 10",
            (user["user_id"],)
        )
        my_orders = rows_to_dicts(cursor.fetchall())

        ## count of products available
        cursor.execute("SELECT COUNT(*) as total FROM PRODUCTS")
        product_count = cursor.fetchone()["total"]

    except Exception as e:
        print(f"Error loading user dashboard: {e}")
        my_orders = []
        product_count = 0
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="user_dashboard.html", context={
        "user": user,
        "my_orders": my_orders,
        "product_count": product_count,
    })


# ---------- USERS (admin only) ----------

@app.get("/users", response_class=HTMLResponse)
async def view_users(request: Request):
    check = require_admin(request)
    if check:
        return check

    user = get_session_user(request)
    q = request.query_params.get("q", "")
    status = request.query_params.get("status")
    message = request.query_params.get("message")

    conn = database.get_connection()
    if conn is None:
        return templates.TemplateResponse(request=request, name="users.html", context={
            "users": [], "search_query": q, "user": user,
            "status": "error", "message": "Database connection failed.",
            "total_users": 0, "active_users": 0,
        })

    cursor = conn.cursor()
    users = []
    total_users = 0
    active_users = 0

    try:
        if q.strip():
            like = f"%{q.strip()}%"
            cursor.execute(
                "SELECT user_id, full_name, email, role, company_name, status, created_at "
                "FROM USERS "
                "WHERE full_name LIKE ? OR email LIKE ? OR role LIKE ? OR company_name LIKE ? "
                "ORDER BY created_at DESC",
                (like, like, like, like)
            )
        else:
            cursor.execute(
                "SELECT user_id, full_name, email, role, company_name, status, created_at "
                "FROM USERS ORDER BY created_at DESC"
            )

        users = rows_to_dicts(cursor.fetchall())
        total_users = len(users)
        for u in users:
            if str(u.get("status", "")).lower() == "active":
                active_users += 1

    except Exception as e:
        print(f"Error fetching users: {e}")
        status = "error"
        message = "Could not load users right now."
        users = []
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="users.html", context={
        "users": users, "search_query": q, "user": user,
        "status": status, "message": message,
        "total_users": total_users, "active_users": active_users,
    })


@app.post("/users/add")
async def add_user(request: Request):
    check = require_admin(request)
    if check:
        return check

    form = await request.form()
    full_name = form.get("full_name", "").strip()
    email = form.get("email", "").strip().lower()
    role = form.get("role", "").strip()
    company_name = form.get("company_name", "").strip()
    status = form.get("status", "Active").strip() or "Active"
    password = form.get("password", "defaultpass").strip()

    if not full_name or not email or not role:
        msg = quote_plus("Please fill all required fields.")
        return RedirectResponse(url=f"/users?status=error&message={msg}", status_code=303)

    conn = database.get_connection()
    if conn is None:
        msg = quote_plus("Database connection failed.")
        return RedirectResponse(url=f"/users?status=error&message={msg}", status_code=303)

    cursor = conn.cursor()
    redirect_url = "/users?status=success&message=User+added+successfully"

    try:
        hashed = database.hash_password(password)
        cursor.execute(
            "INSERT INTO USERS (full_name, email, password, role, company_name, status) VALUES (?, ?, ?, ?, ?, ?)",
            (full_name, email, hashed, role, company_name or None, status)
        )
        conn.commit()
    except Exception as e:
        print(f"Error adding user: {e}")
        conn.rollback()
        msg = quote_plus("Could not add user. Check duplicate email or invalid input.")
        redirect_url = f"/users?status=error&message={msg}"
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=303)


@app.post("/users/delete")
async def delete_user(request: Request):
    check = require_admin(request)
    if check:
        return check

    form = await request.form()
    user_id = form.get("user_id")

    conn = database.get_connection()
    if conn is None:
        msg = quote_plus("Database connection failed.")
        return RedirectResponse(url=f"/users?status=error&message={msg}", status_code=303)

    cursor = conn.cursor()
    redirect_url = "/users?status=success&message=User+removed+successfully"

    try:
        cursor.execute("SELECT order_id FROM ORDERS WHERE requested_by = ? ORDER BY order_id ASC", (user_id,))
        linked = rows_to_dicts(cursor.fetchall())

        if linked:
            ids = [str(row["order_id"]) for row in linked]
            order_list = ", ".join(f"#{oid}" for oid in ids)
            label = "order" if len(ids) == 1 else "orders"
            msg = quote_plus(f"Cannot remove user. Linked {label}: {order_list}")
            redirect_url = f"/users?status=warning&message={msg}"
            conn.rollback()
            return RedirectResponse(url=redirect_url, status_code=303)

        cursor.execute("DELETE FROM USERS WHERE user_id = ?", (user_id,))
        if cursor.rowcount <= 0:
            msg = quote_plus("No matching user found.")
            redirect_url = f"/users?status=warning&message={msg}"
            conn.rollback()
        else:
            conn.commit()

    except Exception as e:
        print(f"Error deleting user: {e}")
        conn.rollback()
        msg = quote_plus("Could not remove user due to related records.")
        redirect_url = f"/users?status=error&message={msg}"
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=303)


# ---------- PRODUCTS ----------

@app.get("/products", response_class=HTMLResponse)
async def view_products(request: Request):
    check = require_admin(request)
    if check:
        return check

    user = get_session_user(request)
    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT p.*, u.full_name AS supplier_name "
            "FROM PRODUCTS p "
            "LEFT JOIN USERS u ON p.supplier_id = u.user_id "
            "ORDER BY p.product_id ASC"
        )
        products = rows_to_dicts(cursor.fetchall())
    except Exception as e:
        print(f"Error fetching products: {e}")
        products = []
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="products.html", context={
        "products": products, "user": user,
    })


# ---------- CREATE ORDER ----------

@app.get("/create-order", response_class=HTMLResponse)
async def create_order_form(request: Request):
    check = require_admin(request)
    if check:
        return check

    user = get_session_user(request)
    sort_by = request.query_params.get("sort_by", "newest")

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    current_sort = clean_sort(sort_by)
    sort_clause = SORT_SQL[current_sort]

    try:
        cursor.execute(
            "SELECT user_id, full_name, email FROM USERS "
            "WHERE role IN ('User', 'Retailer', 'Customer') "
            "ORDER BY full_name ASC"
        )
        customers = rows_to_dicts(cursor.fetchall())

        cursor.execute(
            "SELECT p.product_id, p.product_name, p.selling_price, "
            "COALESCE(s.full_name, 'No Supplier') AS supplier_name "
            "FROM PRODUCTS p "
            "LEFT JOIN USERS s ON p.supplier_id = s.user_id "
            "ORDER BY p.product_name ASC"
        )
        products = rows_to_dicts(cursor.fetchall())

        cursor.execute(
            "SELECT o.order_id, o.order_date, o.status, "
            "u.full_name AS customer_name, "
            "(SELECT p2.product_name FROM ORDER_ITEMS oi2 "
            " JOIN PRODUCTS p2 ON p2.product_id = oi2.product_id "
            " WHERE oi2.order_id = o.order_id ORDER BY oi2.item_id ASC LIMIT 1) AS product_name, "
            "(SELECT oi2.quantity FROM ORDER_ITEMS oi2 "
            " WHERE oi2.order_id = o.order_id ORDER BY oi2.item_id ASC LIMIT 1) AS quantity, "
            "COALESCE((SELECT SUM(oi2.quantity * oi2.unit_price) "
            " FROM ORDER_ITEMS oi2 WHERE oi2.order_id = o.order_id), 0) AS total_amount, "
            "COALESCE((SELECT COUNT(*) FROM ORDER_ITEMS oi2 "
            " WHERE oi2.order_id = o.order_id), 0) AS item_count "
            "FROM ORDERS o "
            "JOIN USERS u ON o.requested_by = u.user_id "
            f"ORDER BY {sort_clause} "
            "LIMIT 8"
        )
        recent_orders = rows_to_dicts(cursor.fetchall())

    except Exception as e:
        print(f"Error loading form data: {e}")
        customers, products, recent_orders = [], [], []
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="create_order.html", context={
        "customers": customers, "products": products,
        "recent_orders": recent_orders, "user": user,
        "current_sort": current_sort, "sort_options": SORT_OPTIONS,
    })


@app.post("/create-order")
async def submit_order(request: Request):
    check = require_admin(request)
    if check:
        return check

    form = await request.form()
    customer_id = form.get("customer_id")
    product_id = form.get("product_id")
    quantity = form.get("quantity", 1)
    sort_by = form.get("sort_by", "newest")

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO ORDERS (requested_by, order_date, status, order_type) VALUES (?, ?, ?, ?)",
            (customer_id, datetime.now().isoformat(), "PENDING", "retail")
        )
        order_id = cursor.lastrowid

        cursor.execute("SELECT selling_price FROM PRODUCTS WHERE product_id = ?", (product_id,))
        row = cursor.fetchone()
        unit_price = row["selling_price"] if row else 0

        cursor.execute(
            "INSERT INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (order_id, product_id, quantity, unit_price)
        )
        cursor.execute(
            "UPDATE INVENTORY SET current_stock = current_stock - ? WHERE product_id = ?",
            (quantity, product_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        print(f"Error submitting order: {e}")
    finally:
        cursor.close()
        conn.close()

    current_sort = clean_sort(sort_by)
    return RedirectResponse(url=f"/create-order?sort_by={quote_plus(current_sort)}", status_code=303)


# ---------- MANAGE ORDERS ----------

@app.get("/manage-orders", response_class=HTMLResponse)
async def manage_orders(request: Request):
    check = require_admin(request)
    if check:
        return check

    user = get_session_user(request)
    sort_by = request.query_params.get("sort_by", "newest")

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    current_sort = clean_sort(sort_by)
    sort_clause = SORT_SQL[current_sort]

    try:
        cursor.execute(
            "SELECT o.order_id, o.requested_by AS customer_id, "
            "u.full_name AS customer_name, o.order_date, o.status, "
            "COALESCE((SELECT SUM(oi.quantity * oi.unit_price) "
            " FROM ORDER_ITEMS oi WHERE oi.order_id = o.order_id), 0) AS total_amount, "
            "COALESCE((SELECT COUNT(*) FROM ORDER_ITEMS oi "
            " WHERE oi.order_id = o.order_id), 0) AS item_count "
            "FROM ORDERS o "
            "JOIN USERS u ON o.requested_by = u.user_id "
            f"ORDER BY {sort_clause}"
        )
        orders = rows_to_dicts(cursor.fetchall())
    except Exception as e:
        print(f"Error fetching orders: {e}")
        orders = []
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="manage_orders.html", context={
        "orders": orders, "user": user,
        "current_sort": current_sort, "sort_options": SORT_OPTIONS,
    })


@app.post("/update-order-status")
async def update_order_status(request: Request):
    check = require_admin(request)
    if check:
        return check

    form = await request.form()
    order_id = form.get("order_id")
    new_status = (form.get("new_status", "")).strip().upper()
    redirect_to = form.get("redirect_to", "/manage-orders")
    sort_by = form.get("sort_by", "newest")

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status FROM ORDERS WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            return RedirectResponse(url="/manage-orders", status_code=303)
        old_status = (row["status"] or "").strip().upper()

        cursor.execute("UPDATE ORDERS SET status = ? WHERE order_id = ?", (new_status, order_id))

        if old_status != "CANCELLED" and new_status == "CANCELLED":
            cursor.execute("SELECT product_id, quantity FROM ORDER_ITEMS WHERE order_id = ?", (order_id,))
            for item in cursor.fetchall():
                cursor.execute(
                    "UPDATE INVENTORY SET current_stock = current_stock + ? WHERE product_id = ?",
                    (item["quantity"], item["product_id"])
                )
        elif old_status == "CANCELLED" and new_status != "CANCELLED":
            cursor.execute("SELECT product_id, quantity FROM ORDER_ITEMS WHERE order_id = ?", (order_id,))
            for item in cursor.fetchall():
                cursor.execute(
                    "UPDATE INVENTORY SET current_stock = current_stock - ? WHERE product_id = ?",
                    (item["quantity"], item["product_id"])
                )

        conn.commit()
    except Exception as e:
        print(f"Error updating status: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    allowed = {"/manage-orders", "/create-order"}
    target = redirect_to if redirect_to in allowed else "/manage-orders"
    current_sort = clean_sort(sort_by)
    return RedirectResponse(url=f"{target}?sort_by={quote_plus(current_sort)}", status_code=303)


# ---------- INVENTORY ----------

@app.get("/inventory", response_class=HTMLResponse)
async def get_inventory(request: Request):
    check = require_admin(request)
    if check:
        return check

    user = get_session_user(request)
    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT p.product_id, p.product_name, i.current_stock, i.min_threshold, i.last_restock_date "
            "FROM PRODUCTS p "
            "JOIN INVENTORY i ON p.product_id = i.product_id "
            "ORDER BY i.current_stock ASC"
        )
        inventory = rows_to_dicts(cursor.fetchall())
    except Exception as e:
        print(f"Error fetching inventory: {e}")
        inventory = []
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="inventory.html", context={
        "inventory": inventory, "user": user,
    })


@app.post("/adjust-stock")
async def adjust_stock(request: Request):
    check = require_admin(request)
    if check:
        return check

    form = await request.form()
    product_id = form.get("product_id")
    new_qty = form.get("new_qty")

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE INVENTORY SET current_stock = ?, last_restock_date = ? WHERE product_id = ?",
            (new_qty, datetime.now().isoformat(), product_id)
        )
        conn.commit()
    except Exception as e:
        print(f"Error adjusting stock: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/inventory", status_code=303)


# ---------- ADMIN DASHBOARD ----------

@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    check = require_admin(request)
    if check:
        return check

    user = get_session_user(request)
    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) as total FROM USERS")
        total_users = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT SUM(oi.quantity * oi.unit_price) as revenue "
            "FROM ORDER_ITEMS oi "
            "JOIN ORDERS o ON oi.order_id = o.order_id "
            "WHERE o.status = 'DELIVERED'"
        )
        total_revenue = cursor.fetchone()["revenue"] or 0

        cursor.execute("SELECT COUNT(*) as total FROM ORDERS WHERE status = 'PENDING'")
        pending_orders = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM INVENTORY WHERE current_stock < min_threshold")
        low_stock = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT p.product_name, SUM(oi.quantity) as total_sold "
            "FROM ORDER_ITEMS oi "
            "JOIN PRODUCTS p ON oi.product_id = p.product_id "
            "GROUP BY p.product_id "
            "ORDER BY total_sold DESC LIMIT 5"
        )
        top_products = rows_to_dicts(cursor.fetchall())

        metrics = {
            "total_users": total_users,
            "total_revenue": total_revenue,
            "pending_orders": pending_orders,
            "low_stock_items": low_stock,
        }
    except Exception as e:
        print(f"Error loading dashboard: {e}")
        metrics = {}
        top_products = []
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "metrics": metrics, "top_products": top_products, "user": user,
    })
