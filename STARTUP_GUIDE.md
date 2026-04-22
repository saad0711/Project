# 🌿 IMS CORE — Team Startup Guide

> **CSE 370 Group Project** · Inventory Management System  
> Get the project running on your machine in under 5 minutes.

---

## ✅ Prerequisites (all platforms)

Before you start, make sure you have **Python 3.10 or higher** installed. To check, open a terminal and run:

```bash
python --version
```
or
```bash
python3 --version
```

If Python is not installed, download it from [python.org/downloads](https://www.python.org/downloads/).

> **Note:** You do **NOT** need MySQL installed. The system automatically creates a local database file (`inventory.db`) the first time it runs.

---

## 📥 Step 1 — Clone the Repository

```bash
git clone https://github.com/AhnafZ778/CSE370.git
cd CSE370
```

---

## 🖥️ Step 2 — Set Up Virtual Environment

Choose the instructions for your operating system below.

---

### 🐧 Linux

```bash
# Create the virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt
```

---

### 🍎 macOS

```bash
# Create the virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install all dependencies
pip install -r requirements.txt
```

---

### 🪟 Windows (Command Prompt)

```cmd
:: Create the virtual environment
python -m venv venv

:: Activate it
venv\Scripts\activate

:: Install all dependencies
pip install -r requirements.txt
```

> **Windows PowerShell users** — if you get an "execution policy" error, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then activate with: `venv\Scripts\Activate.ps1`

---

## 🚀 Step 3 — Run the Application

### 🐧 Linux & 🍎 macOS

You can use the included startup script for a one-click launch:

```bash
chmod +x start_ims.sh
./start_ims.sh
```

**Or run manually:**

```bash
source venv/bin/activate
uvicorn main:app --reload
```

---

### 🪟 Windows

```cmd
:: Activate the environment first
venv\Scripts\activate

:: Start the server
uvicorn main:app --reload
```

---

## 🌐 Step 4 — Open in Browser

Once the server starts, you will see output like this:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Open your browser and go to:

**➡️ [http://127.0.0.1:8000](http://127.0.0.1:8000)**

The app will be fully loaded with demo data automatically. ✅

---

## 🗂️ What Each Page Does

| Page | URL | Description |
|------|-----|-------------|
| Home | `/` | Landing page with quick-access tiles |
| Users | `/users` | View registered users and roles |
| Products | `/products` | Product catalog with cost/margin data |
| New Order | `/create-order` | Place a new customer order |
| Manage Orders | `/manage-orders` | Track and update order statuses |
| Inventory | `/inventory` | Real-time stock levels and alerts |
| Dashboard | `/dashboard` | Analytics hub with KPI metrics |

---

## 🛑 How to Stop the Server

Press `Ctrl + C` in the terminal window where the server is running.

---

## 🐛 Troubleshooting

### ❌ `python` command not found (Linux/macOS)
Use `python3` instead of `python` in all commands.

### ❌ `uvicorn: command not found`
This means your virtual environment is not activated. Re-run the activate command for your OS (Step 2) and try again.

### ❌ Port already in use
Run on a different port:
```bash
uvicorn main:app --reload --port 8001
```
Then open [http://127.0.0.1:8001](http://127.0.0.1:8001).

### ❌ Pages load but show no data
The database file will be created automatically the first time you run the server. If it still shows nothing, delete `inventory.db` and restart — it will rebuild fresh.

```bash
# Linux / macOS
rm inventory.db

# Windows
del inventory.db
```

### ❌ Git clone fails (SSH key not set up)
Use HTTPS instead:
```bash
git clone https://github.com/AhnafZ778/CSE370.git
```

---

## 💡 Pro Tips

- **Keep the terminal open** while using the app — closing it stops the server.
- The `--reload` flag means the server **auto-restarts** whenever you save a `.py` file. No need to restart manually.
- Your local `inventory.db` file is **not tracked by git** — any data you add or change is local to your machine only.

---

*Questions? Ping the group chat. Happy coding!* 🚀
