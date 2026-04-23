from fastapi import FastAPI, Request, Form, Depends
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
import database
from datetime import datetime

app = FastAPI(title="Inventory Management System")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

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
async def view_users(request: Request):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor(dictionary=True)
    
    try:
        sql = "SELECT user_id, full_name, email, role, company_name, status, created_at FROM USERS ORDER BY created_at DESC"
        cursor.execute(sql)
        users = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching users: {e}")
        users = []
    finally:
        cursor.close()
        db.close()
        
    return templates.TemplateResponse(request=request, name="users.html", context={"users": users})

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
async def create_order_form(request: Request):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor(dictionary=True)
    
    try:
        # Get customers and products for the select inputs
        cursor.execute("SELECT user_id, full_name, email FROM USERS WHERE role = 'Customer' OR role = 'Retailer'")
        customers = cursor.fetchall()
        
        cursor.execute("SELECT product_id, product_name, selling_price FROM PRODUCTS")
        products = cursor.fetchall()

        cursor.execute("""
            SELECT o.order_id, o.order_date, o.status,
                   u.full_name AS customer_name,
                   p.product_name,
                   oi.quantity
            FROM ORDERS o
            JOIN USERS u ON o.requested_by = u.user_id
            LEFT JOIN ORDER_ITEMS oi ON o.order_id = oi.order_id
            LEFT JOIN PRODUCTS p ON oi.product_id = p.product_id
            ORDER BY o.order_date DESC, o.order_id DESC
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
        "recent_orders": recent_orders
    })

@app.post("/create-order")
async def submit_order(
    request: Request, 
    customer_id: int = Form(...), 
    product_id: int = Form(...), 
    quantity: int = Form(...)
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
        
    return RedirectResponse(url="/create-order", status_code=303)

# Feature 4: Order Approval Workflow
@app.get("/manage-orders", response_class=HTMLResponse)
async def manage_orders(request: Request):
    db = database.get_db_connection()
    if db is None: return HTMLResponse("DB Connection Failed", status_code=500)
    cursor = db.cursor(dictionary=True)
    
    try:
        sql = """
            SELECT o.order_id, o.requested_by as customer_id, u.full_name as customer_name, 
                   o.order_date, o.status,
                   COALESCE(SUM(oi.quantity * oi.unit_price), 0) as total_amount
            FROM ORDERS o
            JOIN USERS u ON o.requested_by = u.user_id
            LEFT JOIN ORDER_ITEMS oi ON o.order_id = oi.order_id
            GROUP BY o.order_id
            ORDER BY o.order_date DESC
        """
        cursor.execute(sql)
        orders = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching orders: {e}")
        orders = []
    finally:
        cursor.close()
        db.close()
        
    return templates.TemplateResponse(request=request, name="manage_orders.html", context={"orders": orders})

@app.post("/update-order-status")
async def update_order_status(
    order_id: int = Form(...),
    new_status: str = Form(...),
    redirect_to: str = Form("/manage-orders")
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
    return RedirectResponse(url=target, status_code=303)

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
