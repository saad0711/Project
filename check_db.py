import database
import sqlite3
import os

def check_connection():
    print("Checking database connection...")
    conn = database.get_db_connection()
    if conn is None:
        print("❌ Connection failed.")
        return

    print("✅ Connection successful!")
    cursor = conn.cursor()
    try:
        # Works for both MySQL and SQLite
        if isinstance(conn, database._SQLiteConnection):
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        else:
            cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print(f"📋 Tables found: {[list(t.values())[0] for t in tables]}")
        print("\nRunning data checks...")
        for table in ['USERS', 'PRODUCTS', 'INVENTORY', 'ORDERS', 'ORDER_ITEMS']:
            try:
                cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                row = cursor.fetchone()
                print(f"   ✅ {table}: {row['cnt']} rows")
            except Exception as e:
                print(f"   ❌ {table}: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    check_connection()
