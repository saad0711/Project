from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import database
from datetime import datetime
from urllib.parse import quote_plus

app = FastAPI(title="Inventory Management System")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ORDER_SORT_OPTIONS = [
    {"value": "newest", "label": "Newest First"},
    {"value": "oldest", "label": "Oldest First"},
    {"value": "highest_total", "label": "Highest Total"},
    {"value": "lowest_total", "label": "Lowest Total"},
    {"value": "customer_az", "label": "Customer A-Z"},
    {"value": "customer_za", "label": "Customer Z-A"},
    {"value": "status", "label": "Status"},
    {"value": "most_items", "label": "Most Items"},
]

ORDER_SORT_SQL = {
    "newest": "o.order_date DESC, o.order_id DESC",
    "oldest": "o.order_date ASC, o.order_id ASC",
    "highest_total": "total_amount DESC, o.order_date DESC, o.order_id DESC",
    "lowest_total": "total_amount ASC, o.order_date ASC, o.order_id ASC",
    "customer_az": "u.full_name ASC, o.order_id ASC",
    "customer_za": "u.full_name DESC, o.order_id DESC",
    "status": "o.status ASC, o.order_date DESC, o.order_id DESC",
    "most_items": "item_count DESC, o.order_date DESC, o.order_id DESC",
}


def _normalize_order_sort(sort_by: str) -> str:
    normalized = (sort_by or "newest").strip().lower()
    return normalized if normalized in ORDER_SORT_SQL else "newest"

# ==========================================
# CORE ROUTES
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Home page routing to the core application features."""
    return templates.TemplateResponse(request=request, name="base.html")

# ==========================================
# TEAM MEMBER 1: CORE ENTITIES
# ==========================================

# Feature 1: User & Role Management
@app.get("/users", response_class=HTMLResponse)
async def view_users(request: Request, q: str = ""):
    db = database.get_db_connection()
    if db is None:
        return templates.TemplateResponse(
            request=request,
            name="users.html",
            context={
                "users": [],
                "search_query": q,
                "status": "error",
                "message": "Database connection failed. Start MySQL and refresh.",
                "total_users": 0,
                "active_users": 0,
            },
        )

    cursor = db.cursor(dictionary=True)
    status = request.query_params.get("status")
    message = request.query_params.get("message")
    users = []
    total_users = 0
    active_users = 0
    
    try:
        if q.strip():
            sql = """
                SELECT user_id, full_name, email, role, company_name, status, created_at
                FROM USERS
                WHERE full_name LIKE %s
                   OR email LIKE %s
                   OR role LIKE %s
                   OR company_name LIKE %s
                ORDER BY created_at DESC
            """
            like_pattern = f"%{q.strip()}%"
            cursor.execute(sql, (like_pattern, like_pattern, like_pattern, like_pattern))
        else:
            sql = """
                SELECT user_id, full_name, email, role, company_name, status, created_at
                FROM USERS
                ORDER BY created_at DESC
            """
            cursor.execute(sql)

        users = cursor.fetchall()
        total_users = len(users)
        active_users = sum(1 for user in users if str(user.get("status", "")).lower() == "active")
    except Exception as e:
        print(f"Error fetching users: {e}")
        status = "error"
        message = "Could not load users right now."
        users = []
    finally:
        cursor.close()
        db.close()
        
    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={
            "users": users,
            "search_query": q,
            "status": status,
            "message": message,
            "total_users": total_users,
            "active_users": active_users,
        },
    )

@app.post("/users/add")
async def add_user(
    full_name: str = Form(...),
    email: str = Form(...),
    role: str = Form(...),
    company_name: str = Form(""),
    status: str = Form("Active"),
):
    full_name = full_name.strip()
    email = email.strip().lower()
    role = role.strip()
    company_name = company_name.strip()
    status = status.strip() or "Active"

    if not full_name or not email or not role:
        message = quote_plus("Please fill all required fields.")
        return RedirectResponse(url=f"/users?status=error&message={message}", status_code=303)

    db = database.get_db_connection()
    if db is None:
        message = quote_plus("Database connection failed.")
        return RedirectResponse(url=f"/users?status=error&message={message}", status_code=303)

    cursor = db.cursor()
    redirect_url = "/users?status=success&message=User+added+successfully"
    try:
        sql = "INSERT INTO USERS (full_name, email, role, company_name, status) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(sql, (full_name, email, role, company_name or None, status))
        db.commit()
    except Exception as e:
        print(f"Error adding user: {e}")
        db.rollback()
        message = quote_plus("Could not add user. Check duplicate email or invalid input.")
        redirect_url = f"/users?status=error&message={message}"
    finally:
        cursor.close()
        db.close()
    return RedirectResponse(url=redirect_url, status_code=303)

@app.post("/users/delete")
async def delete_user(user_id: int = Form(...)):
    db = database.get_db_connection()
    if db is None:
        message = quote_plus("Database connection failed.")
        return RedirectResponse(url=f"/users?status=error&message={message}", status_code=303)

    cursor = db.cursor(dictionary=True)
    redirect_url = "/users?status=success&message=User+removed+successfully"
    try:
        # Check linked orders first and return exact order IDs.
        cursor.execute(
            "SELECT order_id FROM ORDERS WHERE requested_by = %s ORDER BY order_id ASC",
            (user_id,),
        )
        linked_orders = cursor.fetchall() or []

        if linked_orders:
            order_ids = [str(order.get("order_id")) for order in linked_orders if order.get("order_id") is not None]
            order_list = ", ".join(f"#{order_id}" for order_id in order_ids)
            label = "order number" if len(order_ids) == 1 else "order numbers"
            message = quote_plus(f"Cannot remove user. Linked {label}: {order_list}")
            redirect_url = f"/users?status=warning&message={message}"
            db.rollback()
            return RedirectResponse(url=redirect_url, status_code=303)

        sql = "DELETE FROM USERS WHERE user_id = %s"
        cursor.execute(sql, (user_id,))
        if cursor.rowcount <= 0:
            message = quote_plus("No matching user found.")
            redirect_url = f"/users?status=warning&message={message}"
            db.rollback()
        else:
            db.commit()
    except Exception as e:
        print(f"Error deleting user: {e}")
        db.rollback()
        message = quote_plus("Could not remove user due to related records. Please review linked data and try again.")
        redirect_url = f"/users?status=error&message={message}"
    finally:
        cursor.close()
        db.close()
    return RedirectResponse(url=redirect_url, status_code=303)

# Feature 2: Product Catalog
@app.get("/products", response_class=HTMLResponse)
async def view_products(request: Request):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor(dictionary=True)
    
    try:
        sql = """
            SELECT p.*, u.full_name AS supplier_name 
            FROM PRODUCTS p 
            LEFT JOIN USERS u ON p.supplier_id = u.user_id 
            ORDER BY p.product_id ASC
        """
        cursor.execute(sql)
        products = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching products: {e}")
        products = []
    finally:
        cursor.close()
        db.close()
        
    return templates.TemplateResponse(request=request, name="products.html", context={"products": products})

# ==========================================
# TEAM MEMBER 2: TRANSACTION FLOWS
# ==========================================

# Feature 3: Order Creation & Cart
@app.get("/create-order", response_class=HTMLResponse)
async def create_order_form(request: Request, sort_by: str = "newest"):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor(dictionary=True)
    current_sort = _normalize_order_sort(sort_by)
    sort_clause = ORDER_SORT_SQL[current_sort]
    
    try:
        # Get customers and products for the select inputs
        cursor.execute("""
            SELECT u.user_id, u.full_name, u.email
            FROM USERS u
            WHERE u.role IN ('Customer', 'Retailer')
            ORDER BY u.full_name ASC
        """)
        customers = cursor.fetchall()
        
        cursor.execute("""
            SELECT p.product_id, p.product_name, p.selling_price,
                   COALESCE(s.full_name, 'No Supplier') AS supplier_name
            FROM PRODUCTS p
            LEFT JOIN USERS s ON p.supplier_id = s.user_id
            ORDER BY p.product_name ASC
        """)
        products = cursor.fetchall()

        cursor.execute("""
            WITH item_summary AS (
                SELECT
                    oi.order_id,
                    SUM(oi.quantity * oi.unit_price) AS total_amount,
                    COUNT(*) AS item_count
                FROM ORDER_ITEMS oi
                GROUP BY oi.order_id
            )
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
                COALESCE(s.total_amount, 0) AS total_amount,
                COALESCE(s.item_count, 0) AS item_count
            FROM ORDERS o
            JOIN USERS u ON o.requested_by = u.user_id
            LEFT JOIN item_summary s ON s.order_id = o.order_id
            ORDER BY {sort_clause}
            LIMIT 8
        """)
        recent_orders = cursor.fetchall()
    except Exception as e:
        print(f"Error loading form data: {e}")
        customers, products, recent_orders = [], [], []
    finally:
        cursor.close()
        db.close()
        
    return templates.TemplateResponse(request=request, name="create_order.html", context={
        "customers": customers, 
        "products": products,
        "recent_orders": recent_orders,
        "current_sort": current_sort,
        "sort_options": ORDER_SORT_OPTIONS,
    })

@app.post("/create-order")
async def submit_order(
    request: Request, 
    customer_id: int = Form(...), 
    product_id: int = Form(...), 
    quantity: int = Form(...),
    sort_by: str = Form("newest")
):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor()
    
    try:
        # Start Transaction
        db.start_transaction()
        
        # 1. Create the Order
        sql_order = "INSERT INTO ORDERS (requested_by, order_date, status, order_type) VALUES (%s, %s, %s, %s)"
        cursor.execute(sql_order, (customer_id, datetime.now(), 'PENDING', 'retail'))
        order_id = cursor.lastrowid
        
        # 2. Get Product Price
        cursor.execute("SELECT selling_price FROM PRODUCTS WHERE product_id = %s", (product_id,))
        res = cursor.fetchone()
        if isinstance(res, dict):
            unit_price = res.get("selling_price", 0)
        else:
            unit_price = res[0] if res else 0
        
        # 3. Add Item to Order
        sql_item = "INSERT INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price) VALUES (%s, %s, %s, %s)"
        cursor.execute(sql_item, (order_id, product_id, quantity, unit_price))
        
        # 4. Reserve inventory for pending order.
        sql_inventory = "UPDATE INVENTORY SET current_stock = current_stock - %s WHERE product_id = %s"
        cursor.execute(sql_inventory, (quantity, product_id))
        
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error submitting order: {e}")
    finally:
        cursor.close()
        db.close()
        
    current_sort = _normalize_order_sort(sort_by)
    return RedirectResponse(url=f"/create-order?sort_by={quote_plus(current_sort)}", status_code=303)

# Feature 4: Order Approval Workflow
@app.get("/manage-orders", response_class=HTMLResponse)
async def manage_orders(request: Request, sort_by: str = "newest"):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor(dictionary=True)
    current_sort = _normalize_order_sort(sort_by)
    sort_clause = ORDER_SORT_SQL[current_sort]
    
    try:
        sql = """
            WITH order_summary AS (
                SELECT
                    oi.order_id,
                    SUM(oi.quantity * oi.unit_price) AS total_amount,
                    COUNT(*) AS item_count
                FROM ORDER_ITEMS oi
                GROUP BY oi.order_id
            )
            SELECT
                o.order_id,
                o.requested_by AS customer_id,
                u.full_name AS customer_name,
                o.order_date,
                o.status,
                COALESCE(s.total_amount, 0) AS total_amount,
                COALESCE(s.item_count, 0) AS item_count
            FROM ORDERS o
            JOIN USERS u ON o.requested_by = u.user_id
            LEFT JOIN order_summary s ON s.order_id = o.order_id
            ORDER BY {sort_clause}
        """
        cursor.execute(sql)
        orders = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching orders: {e}")
        orders = []
    finally:
        cursor.close()
        db.close()
        
    return templates.TemplateResponse(request=request, name="manage_orders.html", context={
        "orders": orders,
        "current_sort": current_sort,
        "sort_options": ORDER_SORT_OPTIONS,
    })

@app.post("/update-order-status")
async def update_order_status(
    order_id: int = Form(...),
    new_status: str = Form(...),
    redirect_to: str = Form("/manage-orders"),
    sort_by: str = Form("newest")
):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor()
    
    try:
        normalized_status = (new_status or "").strip().upper()

        cursor.execute("SELECT status FROM ORDERS WHERE order_id = %s", (order_id,))
        status_row = cursor.fetchone()
        if not status_row:
            return RedirectResponse(url="/manage-orders", status_code=303)

        if isinstance(status_row, dict):
            current_status = (status_row.get("status") or "").strip().upper()
        else:
            current_status = (status_row[0] or "").strip().upper()

        sql = "UPDATE ORDERS SET status = %s WHERE order_id = %s"
        cursor.execute(sql, (normalized_status, order_id))

        # Keep inventory aligned with cancellation toggles.
        if current_status != "CANCELLED" and normalized_status == "CANCELLED":
            cursor.execute("SELECT product_id, quantity FROM ORDER_ITEMS WHERE order_id = %s", (order_id,))
            items = cursor.fetchall()
            for item in items:
                if isinstance(item, dict):
                    product_id = item.get("product_id")
                    quantity = item.get("quantity", 0)
                else:
                    product_id, quantity = item[0], item[1]
                cursor.execute(
                    "UPDATE INVENTORY SET current_stock = current_stock + %s WHERE product_id = %s",
                    (quantity, product_id)
                )
        elif current_status == "CANCELLED" and normalized_status != "CANCELLED":
            cursor.execute("SELECT product_id, quantity FROM ORDER_ITEMS WHERE order_id = %s", (order_id,))
            items = cursor.fetchall()
            for item in items:
                if isinstance(item, dict):
                    product_id = item.get("product_id")
                    quantity = item.get("quantity", 0)
                else:
                    product_id, quantity = item[0], item[1]
                cursor.execute(
                    "UPDATE INVENTORY SET current_stock = current_stock - %s WHERE product_id = %s",
                    (quantity, product_id)
                )

        db.commit()
    except Exception as e:
        print(f"Error updating status: {e}")
        db.rollback()
    finally:
        cursor.close()
        db.close()
    
    allowed_redirects = {"/manage-orders", "/create-order"}
    target = redirect_to if redirect_to in allowed_redirects else "/manage-orders"
    current_sort = _normalize_order_sort(sort_by)
    return RedirectResponse(url=f"{target}?sort_by={quote_plus(current_sort)}", status_code=303)

# ==========================================
# TEAM MEMBER 3: INVENTORY & ANALYTICS
# ==========================================

# Feature 5: Stock Adjustments & Fulfillment
@app.get("/inventory", response_class=HTMLResponse)
async def get_inventory(request: Request):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor(dictionary=True)
    
    try:
        sql = """
            SELECT p.product_id, p.product_name, i.current_stock, i.min_threshold, i.last_restock_date
            FROM PRODUCTS p
            JOIN INVENTORY i ON p.product_id = i.product_id
            ORDER BY i.current_stock ASC
        """
        cursor.execute(sql)
        inventory = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching inventory: {e}")
        inventory = []
    finally:
        cursor.close()
        db.close()
        
    return templates.TemplateResponse(request=request, name="inventory.html", context={"inventory": inventory})

@app.post("/adjust-stock")
async def adjust_stock(request: Request, product_id: int = Form(...), new_qty: int = Form(...)):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor()
    
    try:
        sql = "UPDATE INVENTORY SET current_stock = %s, last_restock_date = %s WHERE product_id = %s"
        cursor.execute(sql, (new_qty, datetime.now(), product_id))
        db.commit()
    except Exception as e:
        print(f"Error adjusting stock: {e}")
        db.rollback()
    finally:
        cursor.close()
        db.close()
    
    return RedirectResponse(url="/inventory", status_code=303)

# Feature 6: Dashboard & Analytics
@app.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor(dictionary=True)
    
    try:
        # 1. Total Users
        cursor.execute("SELECT COUNT(*) as total FROM USERS")
        total_users = cursor.fetchone()['total']
        
        # 2. Total Revenue (Delivered Orders)
        cursor.execute("""
            SELECT SUM(oi.quantity * oi.unit_price) as revenue 
            FROM ORDER_ITEMS oi 
            JOIN ORDERS o ON oi.order_id = o.order_id 
            WHERE o.status = 'DELIVERED'
        """)
        total_revenue = cursor.fetchone()['revenue'] or 0
        
        # 3. Pending Orders
        cursor.execute("SELECT COUNT(*) as total FROM ORDERS WHERE status = 'PENDING'")
        pending_orders = cursor.fetchone()['total']
        
        # 4. Low Stock Items
        cursor.execute("SELECT COUNT(*) as total FROM INVENTORY WHERE current_stock < min_threshold")
        low_stock_items = cursor.fetchone()['total']
        
        # 5. Top Selling Products
        cursor.execute("""
            SELECT p.product_name, SUM(oi.quantity) as total_sold
            FROM ORDER_ITEMS oi
            JOIN PRODUCTS p ON oi.product_id = p.product_id
            GROUP BY p.product_id
            ORDER BY total_sold DESC
            LIMIT 5
        """)
        top_products = cursor.fetchall()
        
        metrics = {
            "total_users": total_users,
            "total_revenue": total_revenue,
            "pending_orders": pending_orders,
            "low_stock_items": low_stock_items
        }
    except Exception as e:
        print(f"Error loading dashboard: {e}")
        metrics = {}
        top_products = []
    finally:
        cursor.close()
        db.close()
        
    return templates.TemplateResponse(request=request, name="dashboard.html", context={
        "metrics": metrics, 
        "top_products": top_products
    })
