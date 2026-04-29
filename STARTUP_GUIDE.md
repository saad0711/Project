# IMS - Team Setup Guide

> CSE 370 Group Project - Inventory Management System
> Get the project running on your machine in under 5 minutes.

---

## Prerequisites

Make sure you have **Python 3.10+** installed:

```bash
python --version
```
or
```bash
python3 --version
```

If you dont have it, get it from [python.org/downloads](https://www.python.org/downloads/).

> You do NOT need MySQL. The app automatically creates a local `inventory.db` file the first time it runs.

---

## Step 1 - Clone the Repo

```bash
git clone https://github.com/AhnafZ778/CSE370.git
cd CSE370
```

---

## Step 2 - Set Up Virtual Environment

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Windows (Command Prompt)

```cmd
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> PowerShell users - if you get an "execution policy" error, run this first:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```
> Then activate with: `venv\Scripts\Activate.ps1`

---

## Step 3 - Run the App

### Linux / macOS

You can use the startup script:

```bash
chmod +x start_ims.sh
./start_ims.sh
```

Or run manually:

```bash
source venv/bin/activate
uvicorn main:app --reload
```

### Windows

```cmd
venv\Scripts\activate
uvicorn main:app --reload
```

---

## Step 4 - Open in Browser

Once the server starts you should see:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

Go to **http://127.0.0.1:8000** in your browser. The app loads with sample data automatically.

---

## Pages

| Page | URL | What it does |
|------|-----|-------------|
| Home | `/` | Landing page with links to everything |
| Users | `/users` | View, search, add and remove users |
| Products | `/products` | Product list with pricing info |
| New Order | `/create-order` | Place a new order for a customer |
| Manage Orders | `/manage-orders` | Approve, decline or ship orders |
| Inventory | `/inventory` | Stock levels with manual adjustment |
| Dashboard | `/dashboard` | Summary stats and top selling products |

---

## How to Stop

Press `Ctrl + C` in the terminal.

---

## Troubleshooting

### `python` command not found (Linux/macOS)
Use `python3` instead.

### `uvicorn: command not found`
Your venv is not activated. Run the activate command from Step 2 again.

### Port already in use
```bash
uvicorn main:app --reload --port 8001
```
Then open http://127.0.0.1:8001

### Pages show no data
Delete `inventory.db` and restart the server. It will rebuild with fresh data.

```bash
# Linux / macOS
rm inventory.db

# Windows
del inventory.db
```

### Git clone fails
Use HTTPS:
```bash
git clone https://github.com/AhnafZ778/CSE370.git
```

---

## Tips

- Keep the terminal open while using the app, closing it kills the server
- The `--reload` flag auto restarts when you save a `.py` file
- `inventory.db` is not tracked by git, your local data stays local

---

*Questions? Ping the group chat.*
