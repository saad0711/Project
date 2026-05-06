from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
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


def group_order_rows(rows):
    grouped_orders = []
    order_lookup = {}

    for row in rows:
        order_id = row["order_id"]
        order = order_lookup.get(order_id)

        if order is None:
            order = {
                "order_id": order_id,
                "order_date": row["order_date"],
                "status": row["status"],
                "order_type": row["order_type"],
                "customer_name": row["customer_name"],
                "delivery_address": row["delivery_address"],
                "contact_phone": row["contact_phone"],
                "contact_email": row["contact_email"],
                "order_notes": row["order_notes"],
                "archived": row["archived"],
                "line_items": [],
                "item_count": 0,
                "total_amount": 0.0,
            }
            order_lookup[order_id] = order
            grouped_orders.append(order)

        if row["item_id"] is not None:
            line_total = float(row["line_total"] or 0)
            order["line_items"].append({
                "item_id": row["item_id"],
                "product_id": row["product_id"],
                "product_name": row["product_name"],
                "category": row["category"],
                "quantity": row["quantity"],
                "unit_price": row["unit_price"],
                "line_total": line_total,
            })
            order["item_count"] += 1
            order["total_amount"] += line_total

    return grouped_orders


def fetch_cart_rows(cursor, user_id):
    cursor.execute(
        "SELECT ci.cart_item_id, ci.user_id, ci.product_id, ci.quantity, ci.updated_at, "
        "p.product_name, p.category, p.selling_price, "
        "COALESCE(i.current_stock, 0) AS current_stock, "
        "(ci.quantity * p.selling_price) AS line_total "
        "FROM CART_ITEMS ci "
        "JOIN PRODUCTS p ON p.product_id = ci.product_id "
        "LEFT JOIN INVENTORY i ON i.product_id = p.product_id "
        "WHERE ci.user_id = ? "
        "ORDER BY ci.updated_at DESC, ci.cart_item_id ASC",
        (user_id,)
    )
    cart_rows = rows_to_dicts(cursor.fetchall())
    cart_total = sum(float(row["line_total"] or 0) for row in cart_rows)
    cart_units = sum(int(row["quantity"] or 0) for row in cart_rows)
    return cart_rows, cart_total, cart_units


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
        elif user["role"] == "Supplier":
            return RedirectResponse(url="/supplier-dashboard", status_code=303)
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
        elif user["role"] == "Supplier":
            return RedirectResponse(url="/supplier-dashboard", status_code=303)
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
    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")
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
            "SELECT p.product_id, p.product_name, p.category, p.selling_price, "
            "COALESCE(i.current_stock, 0) AS current_stock "
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
                    "SELECT p.product_id, p.product_name, p.category, p.selling_price, "
                    "COALESCE(i.current_stock, 0) AS current_stock "
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
        "error": error,
        "success": success,
        "my_orders": my_orders,
        "product_count": product_count,
        "available_products": available_products,
        "my_products": my_products,
        "supplier_info": supplier_info
    })


# ---------- SUPPLIER DASHBOARD ----------

@app.get("/supplier-dashboard", response_class=HTMLResponse)
async def supplier_dashboard(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    if user["role"] != "Supplier":
        return RedirectResponse(url="/user-dashboard", status_code=303)

    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")
    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        # Supplier Profile
        cursor.execute("SELECT contact_phone, address, rating FROM SUPPLIERS WHERE user_id = ?", (user["user_id"],))
        supplier_info = cursor.fetchone()

        if not supplier_info:
            cursor.execute("INSERT INTO SUPPLIERS (user_id) VALUES (?)", (user["user_id"],))
            conn.commit()
            cursor.execute("SELECT contact_phone, address, rating FROM SUPPLIERS WHERE user_id = ?", (user["user_id"],))
            supplier_info = cursor.fetchone()

        # Product & Stock Overview
        cursor.execute('''
            SELECT p.product_id, p.product_name, p.category, p.selling_price, COALESCE(i.current_stock, 0) as current_stock 
            FROM PRODUCTS p 
            LEFT JOIN INVENTORY i ON p.product_id = i.product_id 
            WHERE p.supplier_id = (SELECT supplier_id FROM SUPPLIERS WHERE user_id = ?)
        ''', (user["user_id"],))
        my_products = rows_to_dicts(cursor.fetchall())

        # Personal Order Tracking
        cursor.execute('''
            SELECT o.order_id, o.order_date, o.status, 
            COALESCE((SELECT SUM(oi.quantity * oi.unit_price) 
             FROM ORDER_ITEMS oi WHERE oi.order_id = o.order_id), 0) AS total_amount 
            FROM ORDERS o WHERE o.requested_by = ? AND o.archived = 0 
            ORDER BY o.order_date DESC LIMIT 10
        ''', (user["user_id"],))
        my_orders = rows_to_dicts(cursor.fetchall())

        # Low-Stock Widget
        cursor.execute('''
            SELECT p.product_name, i.current_stock, i.min_threshold 
            FROM PRODUCTS p 
            JOIN INVENTORY i ON p.product_id = i.product_id 
            WHERE p.supplier_id = (SELECT supplier_id FROM SUPPLIERS WHERE user_id = ?) 
              AND i.current_stock < i.min_threshold
        ''', (user["user_id"],))
        low_stock_items = rows_to_dicts(cursor.fetchall())

        # "Top Sellers" Quick Analytics
        cursor.execute('''
            SELECT p.product_name, SUM(oi.quantity) as sold 
            FROM ORDER_ITEMS oi 
            JOIN PRODUCTS p ON oi.product_id = p.product_id 
            WHERE p.supplier_id = (SELECT supplier_id FROM SUPPLIERS WHERE user_id = ?) 
            GROUP BY p.product_name 
            ORDER BY sold DESC 
            LIMIT 5
        ''', (user["user_id"],))
        top_sellers = rows_to_dicts(cursor.fetchall())

        # Financial Performance Ledger
        # Total Revenue
        cursor.execute('''
            SELECT SUM(quantity * unit_price) as total_revenue 
            FROM ORDER_ITEMS 
            WHERE product_id IN (SELECT product_id FROM PRODUCTS WHERE supplier_id = (SELECT supplier_id FROM SUPPLIERS WHERE user_id = ?))
        ''', (user["user_id"],))
        row = cursor.fetchone()
        total_revenue = row["total_revenue"] if row and row["total_revenue"] else 0

        # Sales Volume
        cursor.execute('''
            SELECT SUM(quantity) as total_volume 
            FROM ORDER_ITEMS 
            WHERE product_id IN (SELECT product_id FROM PRODUCTS WHERE supplier_id = (SELECT supplier_id FROM SUPPLIERS WHERE user_id = ?))
        ''', (user["user_id"],))
        row = cursor.fetchone()
        total_volume = row["total_volume"] if row and row["total_volume"] else 0

        # Efficiency (Most Profitable Items)
        cursor.execute('''
            SELECT product_name, (selling_price - unit_cost) as profit_margin 
            FROM PRODUCTS 
            WHERE supplier_id = (SELECT supplier_id FROM SUPPLIERS WHERE user_id = ?) 
            ORDER BY profit_margin DESC 
            LIMIT 5
        ''', (user["user_id"],))
        efficiency = rows_to_dicts(cursor.fetchall())

    except Exception as e:
        print(f"Error loading supplier dashboard: {e}")
        supplier_info = None
        my_products = []
        my_orders = []
        low_stock_items = []
        top_sellers = []
        total_revenue = 0
        total_volume = 0
        efficiency = []
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="supplier_dashboard.html", context={
        "user": user,
        "error": error,
        "success": success,
        "supplier_info": supplier_info,
        "my_products": my_products,
        "my_orders": my_orders,
        "low_stock_items": low_stock_items,
        "top_sellers": top_sellers,
        "total_revenue": total_revenue,
        "total_volume": total_volume,
        "efficiency": efficiency
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


@app.get("/cart", response_class=HTMLResponse)
async def cart_page(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cart_items, cart_total, cart_units = fetch_cart_rows(cursor, user["user_id"])
    except Exception as e:
        print(f"Error loading cart: {e}")
        cart_items = []
        cart_total = 0.0
        cart_units = 0
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="cart.html", context={
        "user": user,
        "error": error,
        "success": success,
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_units": cart_units,
    })


@app.post("/cart/add")
async def add_to_cart(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    form = await request.form()
    try:
        product_id = int(form.get("product_id", "0"))
        quantity = int(form.get("quantity", "1"))
    except ValueError:
        return RedirectResponse(url="/user-dashboard?error=Invalid+cart+item", status_code=303)

    if product_id <= 0 or quantity <= 0:
        return RedirectResponse(url="/user-dashboard?error=Invalid+cart+item", status_code=303)

    conn = database.get_connection()
    if conn is None:
        return RedirectResponse(url="/user-dashboard?error=Database+Error", status_code=303)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT p.product_name, COALESCE(i.current_stock, 0) AS current_stock "
            "FROM PRODUCTS p "
            "LEFT JOIN INVENTORY i ON i.product_id = p.product_id "
            "WHERE p.product_id = ?",
            (product_id,)
        )
        product = cursor.fetchone()
        if not product:
            return RedirectResponse(url="/user-dashboard?error=Product+not+found", status_code=303)

        cursor.execute(
            "SELECT quantity FROM CART_ITEMS WHERE user_id = ? AND product_id = ?",
            (user["user_id"], product_id)
        )
        existing_item = cursor.fetchone()
        existing_qty = int(existing_item["quantity"]) if existing_item else 0
        desired_qty = existing_qty + quantity

        if desired_qty > int(product["current_stock"] or 0):
            return RedirectResponse(url="/user-dashboard?error=Not+enough+stock+available", status_code=303)

        cursor.execute(
            "INSERT INTO CART_ITEMS (user_id, product_id, quantity) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id, product_id) DO UPDATE SET quantity = excluded.quantity, updated_at = datetime('now')",
            (user["user_id"], product_id, desired_qty)
        )
        conn.commit()
    except Exception as e:
        print(f"Error adding cart item: {e}")
        conn.rollback()
        return RedirectResponse(url="/user-dashboard?error=Failed+to+add+to+cart", status_code=303)
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/user-dashboard?success=Added+to+cart", status_code=303)


@app.post("/cart/update")
async def update_cart_item(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    form = await request.form()
    try:
        product_id = int(form.get("product_id", "0"))
        quantity = int(form.get("quantity", "1"))
    except ValueError:
        return RedirectResponse(url="/cart?error=Invalid+cart+item", status_code=303)

    if product_id <= 0:
        return RedirectResponse(url="/cart?error=Invalid+cart+item", status_code=303)

    conn = database.get_connection()
    if conn is None:
        return RedirectResponse(url="/cart?error=Database+Error", status_code=303)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT COALESCE(i.current_stock, 0) AS current_stock "
            "FROM PRODUCTS p LEFT JOIN INVENTORY i ON i.product_id = p.product_id "
            "WHERE p.product_id = ?",
            (product_id,)
        )
        product = cursor.fetchone()
        if not product:
            return RedirectResponse(url="/cart?error=Product+not+found", status_code=303)

        if quantity <= 0:
            cursor.execute(
                "DELETE FROM CART_ITEMS WHERE user_id = ? AND product_id = ?",
                (user["user_id"], product_id)
            )
            conn.commit()
            return RedirectResponse(url="/cart?success=Item+removed+from+cart", status_code=303)

        if quantity > int(product["current_stock"] or 0):
            return RedirectResponse(url="/cart?error=Not+enough+stock+available", status_code=303)

        cursor.execute(
            "UPDATE CART_ITEMS SET quantity = ?, updated_at = datetime('now') "
            "WHERE user_id = ? AND product_id = ?",
            (quantity, user["user_id"], product_id)
        )
        if cursor.rowcount <= 0:
            return RedirectResponse(url="/cart?error=Item+not+found+in+cart", status_code=303)

        conn.commit()
    except Exception as e:
        print(f"Error updating cart item: {e}")
        conn.rollback()
        return RedirectResponse(url="/cart?error=Failed+to+update+cart", status_code=303)
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/cart", status_code=303)


@app.post("/cart/remove")
async def remove_cart_item(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    form = await request.form()
    try:
        product_id = int(form.get("product_id", "0"))
    except ValueError:
        return RedirectResponse(url="/cart?error=Invalid+cart+item", status_code=303)

    if product_id <= 0:
        return RedirectResponse(url="/cart?error=Invalid+cart+item", status_code=303)

    conn = database.get_connection()
    if conn is None:
        return RedirectResponse(url="/cart?error=Database+Error", status_code=303)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "DELETE FROM CART_ITEMS WHERE user_id = ? AND product_id = ?",
            (user["user_id"], product_id)
        )
        conn.commit()
    except Exception as e:
        print(f"Error removing cart item: {e}")
        conn.rollback()
        return RedirectResponse(url="/cart?error=Failed+to+remove+item", status_code=303)
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/cart?success=Item+removed+from+cart", status_code=303)


@app.get("/cart/checkout", response_class=HTMLResponse)
async def cart_checkout_page(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cart_items, cart_total, cart_units = fetch_cart_rows(cursor, user["user_id"])
        if not cart_items:
            return RedirectResponse(url="/cart?error=Your+cart+is+empty", status_code=303)
    except Exception as e:
        print(f"Error loading cart checkout page: {e}")
        cart_items = []
        cart_total = 0.0
        cart_units = 0
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="cart_checkout.html", context={
        "user": user,
        "error": error,
        "success": success,
        "cart_items": cart_items,
        "cart_total": cart_total,
        "cart_units": cart_units,
    })


@app.post("/cart/checkout")
async def checkout_cart(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    form = await request.form()
    customer_name = form.get("customer_name", "").strip()
    delivery_address = form.get("delivery_address", "").strip()
    contact_phone = form.get("contact_phone", "").strip()
    contact_email = form.get("contact_email", "").strip()
    order_notes = form.get("order_notes", "").strip()

    if not customer_name:
        customer_name = user["full_name"]
    if not contact_email:
        contact_email = user["email"]

    if not customer_name or not delivery_address or not contact_phone or not contact_email:
        msg = quote_plus("Please fill all required checkout fields.")
        return RedirectResponse(url=f"/cart/checkout?error={msg}", status_code=303)

    conn = database.get_connection()
    if conn is None:
        return RedirectResponse(url="/cart/checkout?error=Database+Error", status_code=303)

    cursor = conn.cursor()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cart_items, _, _ = fetch_cart_rows(cursor, user["user_id"])
        if not cart_items:
            conn.rollback()
            return RedirectResponse(url="/cart?error=Your+cart+is+empty", status_code=303)

        for item in cart_items:
            if int(item["current_stock"] or 0) < int(item["quantity"] or 0):
                conn.rollback()
                msg = quote_plus(f"Not enough stock for {item['product_name']}")
                return RedirectResponse(url=f"/cart/checkout?error={msg}", status_code=303)

        cursor.execute(
            "INSERT INTO ORDERS (requested_by, order_type, status, customer_name, delivery_address, contact_phone, contact_email, order_notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user["user_id"], "Cart", "PENDING", customer_name, delivery_address, contact_phone, contact_email, order_notes or None)
        )
        order_id = cursor.lastrowid

        for item in cart_items:
            cursor.execute(
                "INSERT INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
                (order_id, item["product_id"], item["quantity"], item["selling_price"])
            )
            cursor.execute(
                "UPDATE INVENTORY SET current_stock = current_stock - ? WHERE product_id = ?",
                (item["quantity"], item["product_id"])
            )

        cursor.execute("DELETE FROM CART_ITEMS WHERE user_id = ?", (user["user_id"],))
        conn.commit()
    except Exception as e:
        print(f"Error checking out cart: {e}")
        conn.rollback()
        return RedirectResponse(url="/cart/checkout?error=Failed+to+checkout+cart", status_code=303)
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/recent-orders?success=Order+placed+successfully", status_code=303)


@app.get("/recent-orders", response_class=HTMLResponse)
async def recent_orders(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")
    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT o.order_id, o.order_date, o.status, o.order_type, o.customer_name, "
            "o.delivery_address, o.contact_phone, o.contact_email, o.order_notes, o.archived, "
            "oi.item_id, oi.product_id, p.product_name, p.category, "
            "oi.quantity, oi.unit_price, (oi.quantity * oi.unit_price) AS line_total "
            "FROM ORDERS o "
            "LEFT JOIN ORDER_ITEMS oi ON oi.order_id = o.order_id "
            "LEFT JOIN PRODUCTS p ON p.product_id = oi.product_id "
            "WHERE o.requested_by = ? "
            "ORDER BY o.order_date DESC, o.order_id DESC, oi.item_id ASC",
            (user["user_id"],)
        )
        recent_orders = group_order_rows(cursor.fetchall())
    except Exception as e:
        print(f"Error loading recent orders: {e}")
        recent_orders = []
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="recent_orders.html", context={
        "user": user,
        "recent_orders": recent_orders,
        "error": error,
        "success": success,
    })


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
    q = request.query_params.get("q", "").strip()
    status_filter = request.query_params.get("status", "").strip().upper()
    date_from = request.query_params.get("date_from", "").strip()
    date_to = request.query_params.get("date_to", "").strip()

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    current_sort = clean_sort(sort_by)
    sort_clause = SORT_SQL[current_sort]

    try:
        ## build dynamic WHERE clause based on active filters
        conditions = []
        params = []

        if status_filter == "ARCHIVED":
            conditions.append("o.archived = 1")
        else:
            conditions.append("o.archived = 0")
            if status_filter:
                conditions.append("o.status = ?")
                params.append(status_filter)

        if q:
            conditions.append("(CAST(o.order_id AS TEXT) LIKE ? OR u.full_name LIKE ?)")
            params.extend([f"%{q}%", f"%{q}%"])

        if date_from:
            conditions.append("DATE(o.order_date) >= ?")
            params.append(date_from)

        if date_to:
            conditions.append("DATE(o.order_date) <= ?")
            params.append(date_to)

        where_clause = " AND ".join(conditions)

        cursor.execute(
            f"SELECT o.order_id, o.requested_by AS customer_id, "
            f"u.full_name AS customer_name, o.order_date, o.status, o.archived, "
            f"o.confirmed_at, o.packed_at, o.shipped_at, o.delivered_at, "
            f"COALESCE((SELECT SUM(oi.quantity * oi.unit_price) "
            f" FROM ORDER_ITEMS oi WHERE oi.order_id = o.order_id), 0) AS total_amount, "
            f"COALESCE((SELECT COUNT(*) FROM ORDER_ITEMS oi "
            f" WHERE oi.order_id = o.order_id), 0) AS item_count "
            f"FROM ORDERS o "
            f"JOIN USERS u ON o.requested_by = u.user_id "
            f"WHERE {where_clause} "
            f"ORDER BY {sort_clause}",
            params
        )
        orders = rows_to_dicts(cursor.fetchall())

        ## --- analytics queries ---
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM ORDERS "
            "WHERE DATE(order_date) = DATE('now') AND archived = 0"
        )
        orders_today = cursor.fetchone()["cnt"]

        cursor.execute(
            "SELECT COUNT(*) as cnt FROM ORDERS "
            "WHERE status = 'PENDING' AND archived = 0"
        )
        pending_count = cursor.fetchone()["cnt"]

        cursor.execute(
            "SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0) as revenue "
            "FROM ORDER_ITEMS oi "
            "JOIN ORDERS o ON oi.order_id = o.order_id "
            "WHERE o.status = 'DELIVERED' AND o.archived = 0"
        )
        total_revenue = cursor.fetchone()["revenue"] or 0

        cursor.execute(
            "SELECT p.product_name, SUM(oi.quantity) as total_sold "
            "FROM ORDER_ITEMS oi "
            "JOIN PRODUCTS p ON oi.product_id = p.product_id "
            "JOIN ORDERS o ON oi.order_id = o.order_id "
            "WHERE o.archived = 0 "
            "GROUP BY p.product_id ORDER BY total_sold DESC LIMIT 1"
        )
        top_row = cursor.fetchone()
        top_product = top_row["product_name"] if top_row else "N/A"

        analytics = {
            "orders_today": orders_today,
            "pending_count": pending_count,
            "total_revenue": total_revenue,
            "top_product": top_product,
        }

    except Exception as e:
        print(f"Error fetching orders: {e}")
        orders = []
        analytics = {"orders_today": 0, "pending_count": 0, "total_revenue": 0, "top_product": "N/A"}
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="manage_orders.html", context={
        "orders": orders, "user": user,
        "current_sort": current_sort, "sort_options": SORT_OPTIONS,
        "q": q, "status_filter": status_filter,
        "date_from": date_from, "date_to": date_to,
        "analytics": analytics,
        "error": request.query_params.get("error", ""),
        "success": request.query_params.get("success", ""),
    })


@app.post("/update-order-status")
async def update_order_status(request: Request):
    check = require_admin(request)
    if check:
        return check

    user = get_session_user(request)
    form = await request.form()
    order_id = form.get("order_id")
    new_status = (form.get("new_status", "")).strip().upper()
    redirect_to = form.get("redirect_to", "/manage-orders")
    sort_by = form.get("sort_by", "newest")

    ## valid status transitions
    VALID_STATUSES = {"CONFIRMED", "PACKED", "SHIPPED", "DELIVERED", "CANCELLED"}
    if new_status not in VALID_STATUSES:
        return RedirectResponse(url="/manage-orders", status_code=303)

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    now = datetime.now().isoformat()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT status FROM ORDERS WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        if not row:
            return RedirectResponse(url="/manage-orders", status_code=303)
        old_status = (row["status"] or "").strip().upper()

        ## map status → timestamp column
        ts_col = {"CONFIRMED": "confirmed_at", "PACKED": "packed_at",
                  "SHIPPED": "shipped_at", "DELIVERED": "delivered_at"}.get(new_status)

        if ts_col:
            cursor.execute(
                f"UPDATE ORDERS SET status = ?, {ts_col} = ? WHERE order_id = ?",
                (new_status, now, order_id)
            )
        else:
            cursor.execute("UPDATE ORDERS SET status = ? WHERE order_id = ?", (new_status, order_id))

        ## log into status history
        cursor.execute(
            "INSERT INTO ORDER_STATUS_HISTORY (order_id, status, changed_at, changed_by) VALUES (?, ?, ?, ?)",
            (order_id, new_status, now, user["user_id"])
        )

        ## stock management: restore on cancel, deduct if un-cancelling
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
        success_msg = quote_plus(f"Order #{order_id} updated to {new_status}.")
        allowed = {"/manage-orders", "/create-order"}
        target = redirect_to if redirect_to in allowed else "/manage-orders"
        current_sort = clean_sort(sort_by)
        return RedirectResponse(url=f"{target}?sort_by={quote_plus(current_sort)}&success={success_msg}", status_code=303)
    except Exception as e:
        print(f"Error updating status: {e}")
        conn.rollback()
        err_msg = quote_plus(f"Failed to update order #{order_id}: database may be busy. Please try again.")
        current_sort = clean_sort(sort_by)
        return RedirectResponse(url=f"/manage-orders?sort_by={quote_plus(current_sort)}&error={err_msg}", status_code=303)
    finally:
        cursor.close()
        conn.close()


@app.get("/orders/archive/{order_id}")
async def archive_order(order_id: int, request: Request):
    check = require_admin(request)
    if check:
        return check

    sort_by = request.query_params.get("sort_by", "newest")

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE ORDERS SET archived = 1 "
            "WHERE order_id = ? AND status IN ('DELIVERED', 'CANCELLED')",
            (order_id,)
        )
        conn.commit()
        if cursor.rowcount == 0:
            current_sort = clean_sort(sort_by)
            err_msg = quote_plus("Could not archive order. Make sure it is Delivered or Cancelled.")
            return RedirectResponse(url=f"/manage-orders?sort_by={quote_plus(current_sort)}&error={err_msg}", status_code=303)
    except Exception as e:
        print(f"Error archiving order: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    current_sort = clean_sort(sort_by)
    return RedirectResponse(url=f"/manage-orders?sort_by={quote_plus(current_sort)}&success=Order+archived.", status_code=303)


@app.get("/orders/delete/{order_id}")
async def delete_order(order_id: int, request: Request):
    check = require_admin(request)
    if check:
        return check

    sort_by = request.query_params.get("sort_by", "newest")

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ORDERS WHERE order_id = ? AND archived = 1", (order_id,))
        conn.commit()
    except Exception as e:
        print(f"Error deleting order: {e}")
        conn.rollback()
        err_msg = quote_plus("Failed to delete order. Ensure it is archived first.")
        return RedirectResponse(url=f"/manage-orders?status=ARCHIVED&sort_by={quote_plus(clean_sort(sort_by))}&error={err_msg}", status_code=303)
    finally:
        cursor.close()
        conn.close()

    current_sort = clean_sort(sort_by)
    return RedirectResponse(url=f"/manage-orders?status=ARCHIVED&sort_by={quote_plus(current_sort)}&success=Order+permanently+deleted.", status_code=303)


@app.get("/order-detail/{order_id}")
async def order_detail(order_id: int, request: Request):
    check = require_admin(request)
    if check:
        return JSONResponse({"error": "Unauthorized"}, status_code=403)

    conn = database.get_connection()
    if conn is None:
        return JSONResponse({"error": "DB error"}, status_code=500)

    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT o.order_id, o.order_date, o.status, o.order_type, "
            "o.customer_name, o.delivery_address, o.contact_phone, o.contact_email, o.order_notes, "
            "o.confirmed_at, o.packed_at, o.shipped_at, o.delivered_at, "
            "u.full_name, u.email "
            "FROM ORDERS o JOIN USERS u ON o.requested_by = u.user_id "
            "WHERE o.order_id = ?",
            (order_id,)
        )
        order = cursor.fetchone()
        if not order:
            return JSONResponse({"error": "Not found"}, status_code=404)
        order_dict = dict(order)

        ## get order items with current inventory info
        cursor.execute(
            "SELECT oi.product_id, p.product_name, p.category, "
            "oi.quantity, oi.unit_price, (oi.quantity * oi.unit_price) as line_total, "
            "COALESCE(i.current_stock, 0) as current_stock "
            "FROM ORDER_ITEMS oi "
            "JOIN PRODUCTS p ON p.product_id = oi.product_id "
            "LEFT JOIN INVENTORY i ON i.product_id = p.product_id "
            "WHERE oi.order_id = ?",
            (order_id,)
        )
        items = rows_to_dicts(cursor.fetchall())

        ## get status change history
        cursor.execute(
            "SELECT h.status, h.changed_at, COALESCE(u.full_name, 'System') as changed_by "
            "FROM ORDER_STATUS_HISTORY h "
            "LEFT JOIN USERS u ON h.changed_by = u.user_id "
            "WHERE h.order_id = ? ORDER BY h.changed_at ASC",
            (order_id,)
        )
        history = rows_to_dicts(cursor.fetchall())

        return JSONResponse({"order": order_dict, "items": items, "history": history})
    except Exception as e:
        print(f"Error fetching order detail: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)
    finally:
        cursor.close()
        conn.close()


@app.post("/bulk-update-orders")
async def bulk_update_orders(request: Request):
    check = require_admin(request)
    if check:
        return check

    user = get_session_user(request)
    form = await request.form()
    order_ids = form.getlist("order_ids")
    new_status = (form.get("new_status", "")).strip().upper()
    sort_by = form.get("sort_by", "newest")

    BULK_VALID = {"PACKED", "SHIPPED", "DELIVERED", "CANCELLED"}
    if new_status not in BULK_VALID or not order_ids:
        current_sort = clean_sort(sort_by)
        return RedirectResponse(url=f"/manage-orders?sort_by={quote_plus(current_sort)}", status_code=303)

    conn = database.get_connection()
    if conn is None:
        return HTMLResponse("DB Connection Failed", status_code=500)

    now = datetime.now().isoformat()
    cursor = conn.cursor()
    ts_col = {"PACKED": "packed_at", "SHIPPED": "shipped_at", "DELIVERED": "delivered_at"}.get(new_status)

    try:
        for oid in order_ids:
            cursor.execute("SELECT status FROM ORDERS WHERE order_id = ?", (oid,))
            row = cursor.fetchone()
            if not row:
                continue
            old_status = (row["status"] or "").strip().upper()

            if ts_col:
                cursor.execute(
                    f"UPDATE ORDERS SET status = ?, {ts_col} = ? WHERE order_id = ?",
                    (new_status, now, oid)
                )
            else:
                cursor.execute("UPDATE ORDERS SET status = ? WHERE order_id = ?", (new_status, oid))

            cursor.execute(
                "INSERT INTO ORDER_STATUS_HISTORY (order_id, status, changed_at, changed_by) VALUES (?, ?, ?, ?)",
                (oid, new_status, now, user["user_id"])
            )

            if old_status != "CANCELLED" and new_status == "CANCELLED":
                cursor.execute("SELECT product_id, quantity FROM ORDER_ITEMS WHERE order_id = ?", (oid,))
                for item in cursor.fetchall():
                    cursor.execute(
                        "UPDATE INVENTORY SET current_stock = current_stock + ? WHERE product_id = ?",
                        (item["quantity"], item["product_id"])
                    )
            elif old_status == "CANCELLED" and new_status != "CANCELLED":
                cursor.execute("SELECT product_id, quantity FROM ORDER_ITEMS WHERE order_id = ?", (oid,))
                for item in cursor.fetchall():
                    cursor.execute(
                        "UPDATE INVENTORY SET current_stock = current_stock - ? WHERE product_id = ?",
                        (item["quantity"], item["product_id"])
                    )

        conn.commit()
    except Exception as e:
        print(f"Error in bulk update: {e}")
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
            "SELECT p.product_id, p.product_name, COALESCE(i.current_stock, 0) as current_stock, "
            "COALESCE(i.min_threshold, 10) as min_threshold, i.last_restock_date "
            "FROM PRODUCTS p "
            "LEFT JOIN INVENTORY i ON p.product_id = i.product_id "
            "ORDER BY current_stock ASC"
        )

        inventory = rows_to_dicts(cursor.fetchall())
        print(f"Fetched inventory: {inventory}")

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
        # 1. Total Inventory Value
        cursor.execute('''
            SELECT SUM(p.unit_cost * i.current_stock) as total_value 
            FROM PRODUCTS p 
            JOIN INVENTORY i ON p.product_id = i.product_id
        ''')
        row = cursor.fetchone()
        total_value = row["total_value"] if row and row["total_value"] else 0

        # 2. Low Stock Alerts
        cursor.execute('''
            SELECT COUNT(*) as low_stock_count 
            FROM INVENTORY 
            WHERE current_stock > 0 AND current_stock < min_threshold
        ''')
        low_stock_count = cursor.fetchone()["low_stock_count"]

        # 3. Out of Stock
        cursor.execute('''
            SELECT COUNT(*) as out_of_stock_count 
            FROM INVENTORY 
            WHERE current_stock = 0
        ''')
        out_of_stock_count = cursor.fetchone()["out_of_stock_count"]

        # 4. Top-Selling Items
        cursor.execute('''
            SELECT p.product_name, SUM(oi.quantity) as total_sold 
            FROM ORDER_ITEMS oi 
            JOIN PRODUCTS p ON oi.product_id = p.product_id 
            JOIN ORDERS o ON oi.order_id = o.order_id 
            WHERE o.archived = 0 
            GROUP BY p.product_id 
            ORDER BY total_sold DESC 
            LIMIT 5
        ''')
        top_products = rows_to_dicts(cursor.fetchall())

        # 5. Recent Activity Feed
        cursor.execute('''
            SELECT o.order_id, u.full_name, o.status, o.order_date 
            FROM ORDERS o 
            JOIN USERS u ON o.requested_by = u.user_id 
            ORDER BY o.order_date DESC 
            LIMIT 5
        ''')
        recent_activity = rows_to_dicts(cursor.fetchall())

        # 6. Purchase Order Status
        cursor.execute('''
            SELECT status, COUNT(*) as status_count 
            FROM ORDERS 
            GROUP BY status
        ''')
        order_status_counts = rows_to_dicts(cursor.fetchall())

        metrics = {
            "total_value": total_value,
            "low_stock_count": low_stock_count,
            "out_of_stock_count": out_of_stock_count,
        }
    except Exception as e:
        print(f"Error loading dashboard: {e}")
        metrics = {}
        top_products = []
        recent_activity = []
        order_status_counts = []
    finally:
        cursor.close()
        conn.close()

    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "metrics": metrics, 
        "top_products": top_products, 
        "recent_activity": recent_activity,
        "order_status_counts": order_status_counts,
        "user": user,
    })



@app.post("/supplier/add-product")
async def supplier_add_product(request: Request):
    check = require_login(request)
    if check:
        return check

    user = get_session_user(request)
    if user["role"] != "Supplier":
        return RedirectResponse(url="/supplier-dashboard?error=Unauthorized", status_code=303)

    form = await request.form()
    product_name = form.get("product_name", "").strip()
    category = form.get("category", "").strip()
    unit_cost = form.get("unit_cost", "0").strip()
    selling_price = form.get("selling_price", "0").strip()
    initial_stock = form.get("initial_stock", "0").strip()
    min_threshold = form.get("min_threshold", "0").strip()

    conn = database.get_connection()
    if conn is None:
        return RedirectResponse(url="/supplier-dashboard?error=DB+Error", status_code=303)

    cursor = conn.cursor()
    try:
        cursor.execute("SELECT supplier_id FROM SUPPLIERS WHERE user_id = ?", (user["user_id"],))
        supplier = cursor.fetchone()
        if not supplier:
            return RedirectResponse(url="/supplier-dashboard?error=Not+registered+as+supplier", status_code=303)

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
        return RedirectResponse(url="/supplier-dashboard?error=Failed+to+add+product", status_code=303)
    finally:
        cursor.close()
        conn.close()

    return RedirectResponse(url="/supplier-dashboard?success=Product+added+successfully", status_code=303)
