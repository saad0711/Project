# Database Schema (Codebase)

Here is the actual database schema extracted from the project's source code, structured in a tabular format similar to the diagram you provided.

### USERS
| <u>user_id</u> | full_name | email | password | role | company_name | status | created_at |
| --- | --- | --- | --- | --- | --- | --- | --- |

### SUPPLIERS
| <u>supplier_id</u> | user_id | contact_phone | address | rating | supply_category | created_at |
| --- | --- | --- | --- | --- | --- | --- |

### PRODUCTS
| <u>product_id</u> | product_name | category | unit_cost | selling_price | supplier_id |
| --- | --- | --- | --- | --- | --- |

### INVENTORY
| <u>product_id</u> | current_stock | min_threshold | last_restock_date |
| --- | --- | --- | --- |

### ORDERS
| <u>order_id</u> | requested_by | order_date | status | order_type | customer_name | delivery_address | contact_phone | contact_email | order_notes | archived | confirmed_at | packed_at | shipped_at | delivered_at |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

### ORDER_STATUS_HISTORY
| <u>history_id</u> | order_id | status | changed_at | changed_by |
| --- | --- | --- | --- | --- |

### ORDER_ITEMS
| <u>item_id</u> | order_id | product_id | quantity | unit_price |
| --- | --- | --- | --- | --- |

### CART_ITEMS
| <u>cart_item_id</u> | user_id | product_id | quantity | created_at | updated_at |
| --- | --- | --- | --- | --- | --- |

---

### Relationships (Foreign Keys)
- **`SUPPLIERS.user_id`** references **`USERS.user_id`**
- **`PRODUCTS.supplier_id`** references **`SUPPLIERS.supplier_id`**
- **`INVENTORY.product_id`** references **`PRODUCTS.product_id`**
- **`ORDERS.requested_by`** references **`USERS.user_id`**
- **`ORDER_STATUS_HISTORY.order_id`** references **`ORDERS.order_id`**
- **`ORDER_STATUS_HISTORY.changed_by`** references **`USERS.user_id`**
- **`ORDER_ITEMS.order_id`** references **`ORDERS.order_id`**
- **`ORDER_ITEMS.product_id`** references **`PRODUCTS.product_id`**
- **`CART_ITEMS.user_id`** references **`USERS.user_id`**
- **`CART_ITEMS.product_id`** references **`PRODUCTS.product_id`**
