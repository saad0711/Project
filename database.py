import sqlite3
import os
import hashlib

## path to the database file, sits right next to this script
DB_PATH = os.path.join(os.path.dirname(__file__), "inventory.db")


## SQL to create all the tables we need
SETUP_TABLES = """
CREATE TABLE IF NOT EXISTS USERS (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT DEFAULT 'User',
    company_name TEXT,
    status TEXT DEFAULT 'Active',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS SUPPLIERS (
    supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    contact_phone TEXT,
    address TEXT,
    rating INTEGER DEFAULT 3,
    supply_category TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES USERS(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS PRODUCTS (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    category TEXT,
    unit_cost REAL NOT NULL,
    selling_price REAL NOT NULL,
    supplier_id INTEGER,
    FOREIGN KEY (supplier_id) REFERENCES SUPPLIERS(supplier_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS INVENTORY (
    product_id INTEGER PRIMARY KEY,
    current_stock INTEGER DEFAULT 0,
    min_threshold INTEGER DEFAULT 10,
    last_restock_date TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ORDERS (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_by INTEGER NOT NULL,
    order_date TEXT DEFAULT (datetime('now')),
    status TEXT DEFAULT 'PENDING',
    order_type TEXT,
    archived INTEGER DEFAULT 0,
    FOREIGN KEY (requested_by) REFERENCES USERS(user_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ORDER_ITEMS (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES ORDERS(order_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id)
);
"""


def hash_password(password):
    ## simple sha256 hash for storing passwords
    return hashlib.sha256(password.encode()).hexdigest()


## some starter data so the app isnt empty when you first run it
def get_seed_data():
    admin_pass = hash_password("admin123")
    user_pass = hash_password("user123")
    supplier_pass = hash_password("supplier123")

    return f"""
INSERT OR IGNORE INTO USERS (user_id, full_name, email, password, role, company_name, status) VALUES
(1, 'Ahnaf Zakaria', 'ahnaf@example.com', '{admin_pass}', 'Admin', 'IMS Core Teams', 'Active'),
(2, 'Global Tech Logistics', 'contact@gtl.com', '{supplier_pass}', 'Supplier', 'GTL Corp', 'Active'),
(3, 'Nexus Synergy', 'sales@nexus.com', '{supplier_pass}', 'Supplier', 'Nexus Synergy', 'Active'),
(4, 'Jane Doe', 'jane@retail.com', '{user_pass}', 'User', "Jane's Boutique", 'Active'),
(5, 'John Smith', 'john@gmail.com', '{user_pass}', 'User', NULL, 'Active');

INSERT OR IGNORE INTO SUPPLIERS (supplier_id, user_id, contact_phone, address, rating, supply_category) VALUES
(1, 2, '+1-555-0101', '45 Industrial Ave, San Jose, CA', 5, 'Electronics'),
(2, 3, '+1-555-0202', '12 Commerce St, Austin, TX', 4, 'Peripherals');

INSERT OR IGNORE INTO PRODUCTS (product_id, product_name, category, unit_cost, selling_price, supplier_id) VALUES
(1, 'Quantum Processor V1', 'Electronics', 150.00, 299.99, 1),
(2, 'Cybernetic Lens', 'Optics', 45.50, 89.00, 1),
(3, 'Aero-Draft Keyboard', 'Peripherals', 30.00, 75.00, 2),
(4, 'Bio-Sync Smartwatch', 'Wearables', 80.00, 159.99, 2),
(5, 'Titanium Chassis M1', 'Hardware', 200.00, 450.00, 1);

INSERT OR IGNORE INTO INVENTORY (product_id, current_stock, min_threshold) VALUES
(1, 15, 5),
(2, 4, 10),
(3, 50, 15),
(4, 2, 5),
(5, 12, 3);

INSERT OR IGNORE INTO ORDERS (order_id, requested_by, status, order_type) VALUES
(1, 4, 'DELIVERED', 'retail'),
(2, 4, 'PENDING', 'retail'),
(3, 5, 'PENDING', 'personal');

INSERT OR IGNORE INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 2, 299.99),
(1, 3, 1, 75.00),
(2, 2, 5, 89.00),
(3, 4, 1, 159.99);
"""


def init_db():
    ## creates the tables and puts in the seed data
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SETUP_TABLES)
    conn.executescript(get_seed_data())
    conn.commit()
    conn.close()


def get_connection():
    ## returns a connection to the sqlite database
    ## if the db file doesnt exist it makes a fresh one first
    if not os.path.exists(DB_PATH):
        print("[DB] No database found, creating a fresh one with sample data...")
        init_db()

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  ## so we can access columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    print("[DB] Connected to SQLite database.")
    return conn
