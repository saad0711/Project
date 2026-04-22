import mysql.connector
import sqlite3
import os
from datetime import datetime

# ─── SQLite Compatibility Layer ────────────────────────────────────────────────
# Wraps a SQLite connection/cursor to behave exactly like mysql-connector-python
# so that main.py needs zero changes.

SQLITE_DB_PATH = os.path.join(os.path.dirname(__file__), "inventory.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS USERS (
    user_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    email     TEXT UNIQUE NOT NULL,
    role      TEXT DEFAULT 'Customer',
    company_name TEXT,
    status    TEXT DEFAULT 'Active',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS PRODUCTS (
    product_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    product_name TEXT NOT NULL,
    category     TEXT,
    unit_cost    REAL NOT NULL,
    selling_price REAL NOT NULL,
    supplier_id  INTEGER,
    FOREIGN KEY (supplier_id) REFERENCES USERS(user_id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS INVENTORY (
    product_id        INTEGER PRIMARY KEY,
    current_stock     INTEGER DEFAULT 0,
    min_threshold     INTEGER DEFAULT 10,
    last_restock_date TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ORDERS (
    order_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_by INTEGER NOT NULL,
    order_date   TEXT DEFAULT (datetime('now')),
    status       TEXT DEFAULT 'PENDING',
    order_type   TEXT,
    FOREIGN KEY (requested_by) REFERENCES USERS(user_id)
);

CREATE TABLE IF NOT EXISTS ORDER_ITEMS (
    item_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id   INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity   INTEGER NOT NULL,
    unit_price REAL NOT NULL,
    FOREIGN KEY (order_id) REFERENCES ORDERS(order_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES PRODUCTS(product_id)
);
"""

SEED_SQL = """
INSERT OR IGNORE INTO USERS (user_id, full_name, email, role, company_name, status) VALUES
(1, 'Ahnaf Zakaria',       'ahnaf@example.com',  'Admin',    'IMS Core Teams',   'Active'),
(2, 'Global Tech Logistics','contact@gtl.com',    'Supplier', 'GTL Corp',         'Active'),
(3, 'Nexus Synergy',        'sales@nexus.com',    'Supplier', 'Nexus Synergy',    'Active'),
(4, 'Jane Doe',             'jane@retail.com',    'Retailer', "Jane's Boutique", 'Active'),
(5, 'John Smith',           'john@gmail.com',     'Customer', NULL,               'Active');

INSERT OR IGNORE INTO PRODUCTS (product_id, product_name, category, unit_cost, selling_price, supplier_id) VALUES
(1, 'Quantum Processor V1', 'Electronics', 150.00, 299.99, 2),
(2, 'Cybernetic Lens',      'Optics',      45.50,  89.00,  2),
(3, 'Aero-Draft Keyboard',  'Peripherals', 30.00,  75.00,  3),
(4, 'Bio-Sync Smartwatch',  'Wearables',   80.00, 159.99,  3),
(5, 'Titanium Chassis M1',  'Hardware',   200.00, 450.00,  2);

INSERT OR IGNORE INTO INVENTORY (product_id, current_stock, min_threshold) VALUES
(1, 15, 5),
(2,  4, 10),
(3, 50, 15),
(4,  2,  5),
(5, 12,  3);

INSERT OR IGNORE INTO ORDERS (order_id, requested_by, status, order_type) VALUES
(1, 4, 'DELIVERED', 'retail'),
(2, 4, 'PENDING',   'retail'),
(3, 5, 'PENDING',   'personal');

INSERT OR IGNORE INTO ORDER_ITEMS (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 2, 299.99),
(1, 3, 1,  75.00),
(2, 2, 5,  89.00),
(3, 4, 1, 159.99);
"""


class _SQLiteCursor:
    """Wraps a sqlite3 cursor to mimic mysql-connector-python's dict cursor."""

    def __init__(self, sqlite_cursor):
        self._cur = sqlite_cursor
        self._columns = []

    def execute(self, sql, params=None):
        # Convert MySQL %s placeholders → SQLite ?
        sql = sql.replace("%s", "?")
        if params:
            self._cur.execute(sql, params)
        else:
            self._cur.execute(sql)
        self._columns = [d[0] for d in (self._cur.description or [])]

    def fetchall(self):
        rows = self._cur.fetchall()
        return [dict(zip(self._columns, row)) for row in rows]

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        return dict(zip(self._columns, row))

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    def close(self):
        self._cur.close()


class _SQLiteConnection:
    """Wraps a sqlite3 connection to mimic mysql-connector-python's API."""

    def __init__(self, conn):
        self._conn = conn
        self._in_transaction = False

    def cursor(self, dictionary=False):
        # dictionary kwarg accepted but ignored – we always return dicts
        return _SQLiteCursor(self._conn.cursor())

    def start_transaction(self):
        self._in_transaction = True

    def commit(self):
        self._conn.commit()
        self._in_transaction = False

    def rollback(self):
        self._conn.rollback()
        self._in_transaction = False

    def close(self):
        self._conn.close()


def _init_sqlite():
    """Create schema and seed data in a fresh SQLite database."""
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.executescript(SCHEMA_SQL)
    conn.executescript(SEED_SQL)
    conn.commit()
    conn.close()


def get_db_connection():
    """
    Returns a database connection.
    Priority: MySQL (env-configured) → SQLite fallback (local file).
    The returned object implements the mysql-connector-python API so that
    all callers in main.py work without modification.
    """
    # ── 1. Try MySQL ──────────────────────────────────────────────────────────
    try:
        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST", "localhost"),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "password"),
            database=os.getenv("DB_NAME", "inventory_db"),
            connection_timeout=3,
        )
        return connection  # native mysql-connector connection
    except mysql.connector.Error as err:
        print(f"[DB] MySQL unavailable ({err}). Falling back to SQLite…")

    # ── 2. Fall back to SQLite ────────────────────────────────────────────────
    try:
        is_new = not os.path.exists(SQLITE_DB_PATH)
        if is_new:
            print("[DB] Initialising fresh SQLite database with seed data…")
            _init_sqlite()
        raw = sqlite3.connect(SQLITE_DB_PATH, check_same_thread=False)
        raw.execute("PRAGMA foreign_keys = ON")
        print("[DB] ✅ Connected to SQLite database.")
        return _SQLiteConnection(raw)
    except Exception as e:
        print(f"[DB] ❌ SQLite connection also failed: {e}")
        return None
