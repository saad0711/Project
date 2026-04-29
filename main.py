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
            return RedirectResponse(url="/home", status_code=303)
        return RedirectResponse(url="/user-dashboard", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/home", response_class=HTMLResponse)
async def admin_home(request: Request):
    check = require_admin(request)
    if check:
        return check
    user = get_session_user(request)
    return templates.TemplateResponse(request=request, name="admin_home.html", context={"user": user})


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

        ## send to the right page based on role
        if user["role"] == "Admin":
            return RedirectResponse(url="/home", status_code=303)
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
        ## get this users orders (only non-archived ones)
        cursor.execute(
            "SELECT o.order_id, o.order_date, o.status, "
            "COALESCE((SELECT SUM(oi.quantity * oi.unit_price) "
            " FROM ORDER_ITEMS oi WHERE oi.order_id = o.order_id), 0) AS total_amount "
            "FROM ORDERS o WHERE o.requested_by = ? AND o.archived = 0 "
            "ORDER BY o.order_date DESC LIMIT 10",
            (user["user_id"],)
        )
        my_orders = rows_to_dicts(cursor.fetchall())

        ## count of products available
        cursor.execute("SELECT COUNT(*) as total FROM PRODUCTS")
        product_count = cursor.fetchone()["total"]

        ## fetch all products for the user to potentially order
        cursor.execute(
            "SELECT p.product_id, p.product_name, p.category, p.selling_price, i.current_stock "
            "FROM PRODUCTS p "
            "LEFT JOIN INVENTORY i ON p.product_id = i.product_id "
            "ORDER BY p.product_name ASC"
        )
        available_products = rows_to_dicts(cursor.fetchall())

        my_products = []
        supplier_info = None
        if user["role"] == "Supplier":
            cursor.execute("SELECT supplier_id, contact_phone, address FROM SUPPLIERS WHERE user_id = ?", (user["user_id"],))
            supplier_info = cursor.fetchone()
            
            ## Auto-create supplier record if it's missing so they can use the dashboard
            if not supplier_info:
                cursor.execute("INSERT INTO SUPPLIERS (user_id) VALUES (?)", (user["user_id"],))
                conn.commit()
                cursor.execute("SELECT supplier_id, contact_phone, address FROM SUPPLIERS WHERE user_id = ?", (user["user_id"],))
                supplier_info = cursor.fetchone()
            if supplier_info:
                cursor.execute(
                    "SELECT p.product_id, p.product_name, p.category, p.selling_price, i.current_stock "
                    "FROM PRODUCTS p "
                    "LEFT JOIN INVENTORY i ON p.product_id = i.product_id "
                    "WHERE p.supplier_id = ? ORDER BY p.product_name ASC",
                    (supplier_info["supplier_id"],)
                )
                my_products = rows_to_dicts(cursor.fetchall())

    except Exception as e:
        print(f"Error loading user dashboard: {e}")
        my_orders = []
        product_count = 0
        available_products = []
        my_products = []
        supplier_info = None
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="user_dashboard.html", context={
        "user": user,
        "my_orders": my_orders,
        "product_count": product_count,
        "available_products": available_products,
        "my_products": my_products,
        "supplier_info": supplier_info
    })

@app.post("/user/place-order")
async def user_place_order(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    form = await request.form()
    product_id = form.get("product_id")
    try:
        quantity = int(form.get("quantity", "1"))
    except ValueError:
        quantity = 1

    if quantity <= 0:
        return RedirectResponse(url="/user-dashboard?error=Invalid+quantity", status_code=303)

    conn = database.get_connection()
    if conn is None:
        return RedirectResponse(url="/user-dashboard?error=Database+Error", status_code=303)

    cursor = conn.cursor()
    try:
        # Check stock
        cursor.execute("SELECT current_stock FROM INVENTORY WHERE product_id = ?", (product_id,))
        inv = cursor.fetchone()
        if not inv or inv["current_stock"] < quantity:
            return RedirectResponse(url="/user-dashboard?error=Not+enough+stock+available", status_code=303)

        # Get product price
        cursor.execute("SELECT selling_price FROM PRODUCTS WHERE product_id = ?", (product_id,))
        prod = cursor.fetchone()
        if not prod:
            return RedirectResponse(url="/user-dashboard?error=Product+not+found", status_code=303)
        unit_price = prod["selling_price"]

        # Create Order
        cursor.execute(
            "INSERT INTO ORDERS (requested_by, order_type, status) VALUES (?, ?, ?)",
            (user["user_id"], "Standard", "PENDING")
        )
        order_id = cursor.lastrowid

        # Insert item
        cursor.execute(
            "INSERT INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
            (order_id, product_id, quantity, unit_price)
        )
        
        # Deduct stock temporarily (until status updates)
        cursor.execute(
            "UPDATE INVENTORY SET current_stock = current_stock - ? WHERE product_id = ?",
            (quantity, product_id)
        )

        conn.commit()
    except Exception as e:
        print(f"Error placing user order: {e}")
        conn.rollback()
        return RedirectResponse(url="/user-dashboard?error=Failed+to+place+order", status_code=303)
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/user-dashboard?success=Order+placed+successfully", status_code=303)


# ---------- USERS (admin only) ----------

## allowed sort columns for users page
USER_SORT_COLS = {
    "name": "u.full_name",
    "email": "u.email",
    "role": "u.role",
    "company": "u.company_name",
    "status": "u.status",
    "date": "u.created_at",
    "orders": "order_count",
}

@app.get("/users", response_class=HTMLResponse)
async def view_users(request: Request):
    check = require_admin(request)
    if check:
        return check

    user = get_session_user(request)
    q = request.query_params.get("q", "")
    sort_by = request.query_params.get("sort_by", "date")
    sort_dir = request.query_params.get("sort_dir", "desc")
    status = request.query_params.get("status")
    message = request.query_params.get("message")

    ## make sure the sort values are safe
    if sort_by not in USER_SORT_COLS:
        sort_by = "date"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "desc"

    sort_column = USER_SORT_COLS[sort_by]
    order_clause = f"{sort_column} {sort_dir.upper()}"

    conn = database.get_connection()
    if conn is None:
        return templates.TemplateResponse(request=request, name="users.html", context={
            "users": [], "search_query": q, "user": user,
            "status": "error", "message": "Database connection failed.",
            "total_users": 0, "active_users": 0,
            "sort_by": sort_by, "sort_dir": sort_dir,
        })

    cursor = conn.cursor()
    users = []
    total_users = 0
    active_users = 0

    try:
        ## uses a nested query to count how many orders each user has
        ## LEFT JOIN would also work but a subquery is easier to read here
        if q.strip():
            like = f"%{q.strip()}%"
            cursor.execute(
                "SELECT u.user_id, u.full_name, u.email, u.role, u.company_name, u.status, u.created_at, "
                "(SELECT COUNT(*) FROM ORDERS o WHERE o.requested_by = u.user_id AND o.archived = 0) AS order_count "
                "FROM USERS u "
                "WHERE (u.full_name LIKE ? OR u.email LIKE ? OR u.role LIKE ? OR u.company_name LIKE ?) AND u.status != 'Deleted' "
                f"ORDER BY {order_clause}",
                (like, like, like, like)
            )
        else:
            cursor.execute(
                "SELECT u.user_id, u.full_name, u.email, u.role, u.company_name, u.status, u.created_at, "
                "(SELECT COUNT(*) FROM ORDERS o WHERE o.requested_by = u.user_id AND o.archived = 0) AS order_count "
                "FROM USERS u "
                "WHERE u.status != 'Deleted' "
                f"ORDER BY {order_clause}"
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
        "sort_by": sort_by, "sort_dir": sort_dir,
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
        cursor.execute("SELECT order_id FROM ORDERS WHERE requested_by = ? AND archived = 0 ORDER BY order_id ASC", (user_id,))
        active_orders = rows_to_dicts(cursor.fetchall())

        if active_orders:
            ids = [str(row["order_id"]) for row in active_orders]
            order_list = ", ".join(f"#{oid}" for oid in ids)
            label = "order" if len(ids) == 1 else "orders"
            msg = quote_plus(f"Cannot remove user. Linked active {label}: {order_list}")
            redirect_url = f"/users?status=warning&message={msg}"
            conn.rollback()
            return RedirectResponse(url=redirect_url, status_code=303)

        cursor.execute("SELECT COUNT(*) as cnt FROM ORDERS WHERE requested_by = ?", (user_id,))
        total_orders = cursor.fetchone()["cnt"]

        if total_orders > 0:
            cursor.execute("UPDATE USERS SET status = 'Deleted' WHERE user_id = ?", (user_id,))
            conn.commit()
        else:
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


# ---------- SUPPLIERS ----------

## allowed sort columns for suppliers page
SUPPLIER_SORT_COLS = {
    "name": "u.full_name",
    "company": "u.company_name",
    "category": "s.supply_category",
    "rating": "s.rating",
    "products": "product_count",
    "revenue": "total_revenue",
    "orders": "order_count",
}

@app.get("/suppliers", response_class=HTMLResponse)
async def view_suppliers(request: Request):
    check = require_admin(request)
    if check:
        return check

    user = get_session_user(request)
    sort_by = request.query_params.get("sort_by", "name")
    sort_dir = request.query_params.get("sort_dir", "asc")
    status = request.query_params.get("status")
    message = request.query_params.get("message")

    if sort_by not in SUPPLIER_SORT_COLS:
        sort_by = "name"
    if sort_dir not in ("asc", "desc"):
        sort_dir = "asc"

    sort_column = SUPPLIER_SORT_COLS[sort_by]
    order_clause = f"{sort_column} {sort_dir.upper()}"

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        ## this is the big query - joins SUPPLIERS to USERS to get the name/email
        ## then uses nested subqueries to pull in data from PRODUCTS and ORDER_ITEMS
        ##
        ## subquery 1: counts how many products this supplier has
        ## subquery 2: sums up all revenue from orders that contain this suppliers products
        ## subquery 3: counts how many distinct orders have items from this supplier
        cursor.execute(
            "SELECT s.supplier_id, s.user_id, s.contact_phone, s.address, "
            "s.rating, s.supply_category, s.created_at, "
            "u.full_name, u.email, u.company_name, "
            "(SELECT COUNT(*) FROM PRODUCTS p WHERE p.supplier_id = s.supplier_id) AS product_count, "
            "(SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0) "
            " FROM ORDER_ITEMS oi "
            " JOIN PRODUCTS p ON oi.product_id = p.product_id "
            " JOIN ORDERS ord ON oi.order_id = ord.order_id "
            " WHERE p.supplier_id = s.supplier_id AND ord.archived = 0) AS total_revenue, "
            "(SELECT COUNT(DISTINCT oi.order_id) "
            " FROM ORDER_ITEMS oi "
            " JOIN PRODUCTS p ON oi.product_id = p.product_id "
            " JOIN ORDERS ord ON oi.order_id = ord.order_id "
            " WHERE p.supplier_id = s.supplier_id AND ord.archived = 0) AS order_count "
            "FROM SUPPLIERS s "
            "JOIN USERS u ON s.user_id = u.user_id "
            f"ORDER BY {order_clause}"
        )
        suppliers = rows_to_dicts(cursor.fetchall())

        ## also get users who are marked as Supplier role but dont have a supplier record yet
        ## so the admin can add them as suppliers
        cursor.execute(
            "SELECT u.user_id, u.full_name, u.email FROM USERS u "
            "LEFT JOIN SUPPLIERS s ON u.user_id = s.user_id "
            "WHERE s.supplier_id IS NULL AND u.status != 'Deleted' "
            "ORDER BY u.full_name ASC"
        )
        available_users = rows_to_dicts(cursor.fetchall())

    except Exception as e:
        print(f"Error fetching suppliers: {e}")
        suppliers = []
        available_users = []
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="suppliers.html", context={
        "suppliers": suppliers, "available_users": available_users, "user": user,
        "sort_by": sort_by, "sort_dir": sort_dir,
        "status": status, "message": message,
    })


@app.post("/suppliers/add")
async def add_supplier(request: Request):
    check = require_admin(request)
    if check:
        return check

    form = await request.form()
    user_id = form.get("user_id")
    contact_phone = form.get("contact_phone", "").strip()
    address = form.get("address", "").strip()
    rating = form.get("rating", "3").strip()
    supply_category = form.get("supply_category", "").strip()

    if not user_id:
        msg = quote_plus("Please select a user to register as supplier.")
        return RedirectResponse(url=f"/suppliers?status=error&message={msg}", status_code=303)

    conn = database.get_connection()
    if conn is None:
        msg = quote_plus("Database connection failed.")
        return RedirectResponse(url=f"/suppliers?status=error&message={msg}", status_code=303)

    cursor = conn.cursor()
    redirect_url = "/suppliers?status=success&message=Supplier+added+successfully"

    try:
        ## check if this user is already a supplier
        cursor.execute("SELECT supplier_id FROM SUPPLIERS WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            msg = quote_plus("This user is already registered as a supplier.")
            redirect_url = f"/suppliers?status=warning&message={msg}"
        else:
            cursor.execute(
                "INSERT INTO SUPPLIERS (user_id, contact_phone, address, rating, supply_category) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, contact_phone or None, address or None, rating, supply_category or None)
            )
            conn.commit()
    except Exception as e:
        print(f"Error adding supplier: {e}")
        conn.rollback()
        msg = quote_plus("Could not add supplier.")
        redirect_url = f"/suppliers?status=error&message={msg}"
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=303)


@app.post("/suppliers/delete")
async def delete_supplier(request: Request):
    check = require_admin(request)
    if check:
        return check

    form = await request.form()
    supplier_id = form.get("supplier_id")

    conn = database.get_connection()
    if conn is None:
        msg = quote_plus("Database connection failed.")
        return RedirectResponse(url=f"/suppliers?status=error&message={msg}", status_code=303)

    cursor = conn.cursor()
    redirect_url = "/suppliers?status=success&message=Supplier+removed+successfully"

    try:
        ## check if this supplier has pending orders
        cursor.execute(
            "SELECT COUNT(*) as pending_count "
            "FROM ORDER_ITEMS oi "
            "JOIN ORDERS o ON oi.order_id = o.order_id "
            "JOIN PRODUCTS p ON oi.product_id = p.product_id "
            "WHERE p.supplier_id = ? AND o.status = 'PENDING' AND o.archived = 0",
            (supplier_id,)
        )
        pending = cursor.fetchone()

        if pending and pending["pending_count"] > 0:
            msg = quote_plus("Cannot remove supplier. They have active pending orders.")
            redirect_url = f"/suppliers?status=warning&message={msg}"
            conn.rollback()
            return RedirectResponse(url=redirect_url, status_code=303)

        cursor.execute("DELETE FROM SUPPLIERS WHERE supplier_id = ?", (supplier_id,))
        if cursor.rowcount <= 0:
            msg = quote_plus("No matching supplier found.")
            redirect_url = f"/suppliers?status=warning&message={msg}"
            conn.rollback()
        else:
            conn.commit()
    except Exception as e:
        print(f"Error deleting supplier: {e}")
        conn.rollback()
        msg = quote_plus("Could not remove supplier.")
        redirect_url = f"/suppliers?status=error&message={msg}"
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url=redirect_url, status_code=303)



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
            "WHERE role IN ('User', 'Retailer', 'Customer') AND status != 'Deleted' "
            "ORDER BY full_name ASC"
        )
        customers = rows_to_dicts(cursor.fetchall())

        cursor.execute(
            "SELECT p.product_id, p.product_name, p.selling_price, "
            "COALESCE(u.full_name, 'No Supplier') AS supplier_name "
            "FROM PRODUCTS p "
            "LEFT JOIN SUPPLIERS s ON p.supplier_id = s.supplier_id "
            "LEFT JOIN USERS u ON s.user_id = u.user_id "
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
            "WHERE o.archived = 0 "
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
            "WHERE o.archived = 0 "
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


@app.post("/orders/archive")
async def archive_order(request: Request):
    check = require_admin(request)
    if check:
        return check

    form = await request.form()
    order_id = form.get("order_id")
    sort_by = form.get("sort_by", "newest")

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        ## only archive orders that are done (delivered or cancelled)
        cursor.execute(
            "UPDATE ORDERS SET archived = 1 "
            "WHERE order_id = ? AND status IN ('DELIVERED', 'CANCELLED')",
            (order_id,)
        )
        conn.commit()
    except Exception as e:
        print(f"Error archiving order: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    current_sort = clean_sort(sort_by)
    return RedirectResponse(url=f"/manage-orders?sort_by={quote_plus(current_sort)}", status_code=303)


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
            "WHERE o.status = 'DELIVERED' AND o.archived = 0"
        )
        total_revenue = cursor.fetchone()["revenue"] or 0

        cursor.execute("SELECT COUNT(*) as total FROM ORDERS WHERE status = 'PENDING' AND archived = 0")
        pending_orders = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) as total FROM INVENTORY WHERE current_stock < min_threshold")
        low_stock = cursor.fetchone()["total"]

        cursor.execute(
            "SELECT p.product_name, SUM(oi.quantity) as total_sold "
            "FROM ORDER_ITEMS oi "
            "JOIN PRODUCTS p ON oi.product_id = p.product_id "
            "JOIN ORDERS o ON oi.order_id = o.order_id "
            "WHERE o.archived = 0 "
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



@app.post("/supplier/add-product")
async def supplier_add_product(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    if user["role"] != "Supplier":
        return RedirectResponse(url="/user-dashboard?error=Unauthorized", status_code=303)

    form = await request.form()
    product_name = form.get("product_name", "").strip()
    category = form.get("category", "").strip()
    unit_cost = form.get("unit_cost", "0").strip()
    selling_price = form.get("selling_price", "0").strip()
    initial_stock = form.get("initial_stock", "0").strip()
    min_threshold = form.get("min_threshold", "0").strip()

    conn = database.get_connection()
    if conn is None:
        return RedirectResponse(url="/user-dashboard?error=DB+Error", status_code=303)

    cursor = conn.cursor()
    try:
        cursor.execute("SELECT supplier_id FROM SUPPLIERS WHERE user_id = ?", (user["user_id"],))
        supplier = cursor.fetchone()
        if not supplier:
            return RedirectResponse(url="/user-dashboard?error=Not+registered+as+supplier", status_code=303)

        supplier_id = supplier["supplier_id"]

        cursor.execute(
            "INSERT INTO PRODUCTS (product_name, category, unit_cost, selling_price, supplier_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (product_name, category, float(unit_cost), float(selling_price), supplier_id)
        )
        product_id = cursor.lastrowid

        cursor.execute(
            "INSERT INTO INVENTORY (product_id, current_stock, min_threshold) VALUES (?, ?, ?)",
            (product_id, int(initial_stock), int(min_threshold))
        )
        conn.commit()
    except Exception as e:
        print(f"Error supplier adding product: {e}")
        conn.rollback()
        return RedirectResponse(url="/user-dashboard?error=Failed+to+add+product", status_code=303)
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/user-dashboard?success=Product+added+successfully", status_code=303)
