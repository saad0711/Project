import database

def check_connection():
    print("Checking database connection...")
    conn = database.get_connection()
    if conn is None:
        print("Connection failed.")
        return

    print("Connection successful!")
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        table_names = [t["name"] for t in tables]
        print(f"Tables found: {table_names}")

        print("\nRunning data checks...")
        for table in ["USERS", "PRODUCTS", "INVENTORY", "ORDERS", "ORDER_ITEMS"]:
            try:
                cursor.execute(f"SELECT COUNT(*) as cnt FROM {table}")
                row = cursor.fetchone()
                print(f"  {table}: {row['cnt']} rows")
            except Exception as e:
                print(f"  {table}: {e}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    check_connection()
