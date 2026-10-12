# 🚀 Deployment Guide

How to deploy the Saliga Sari-Sari Store POS at the store.

## Table of Contents

1. [Deployment Model](#deployment-model)
2. [Hardware Requirements](#hardware-requirements)
3. [Pre-Deployment Checklist](#pre-deployment-checklist)
4. [Step 1: Prepare the Windows PC](#step-1-prepare-the-windows-pc)
5. [Step 2: Install the Project](#step-2-install-the-project)
6. [Step 3: Configure Production Environment](#step-3-configure-production-environment)
7. [Step 4: Initialize the Database](#step-4-initialize-the-database)
8. [Step 5: Change Default Passwords](#step-5-change-default-passwords)
9. [Step 6: Install the Server as a Windows Service](#step-6-install-the-server-as-a-windows-service)
10. [Step 7: Create the GUI Launcher](#step-7-create-the-gui-launcher)
11. [Step 8: Set Up Automated Backups](#step-8-set-up-automated-backups)
12. [Step 9: Configure the Firewall](#step-9-configure-the-firewall)
13. [Step 10: Set Up a Static IP](#step-10-set-up-a-static-ip)
14. [Verifying the Deployment](#verifying-the-deployment)
15. [Day-to-Day Operations](#day-to-day-operations)
16. [Maintenance Schedule](#maintenance-schedule)
17. [Troubleshooting](#troubleshooting)
18. [Emergency Procedures](#emergency-procedures)

---

## Deployment Model

This system is designed to run **on one Windows PC at the store**. It is not a cloud system.

```
┌─────────────────────────────────────────────────────┐
│              Store PC (Windows)                     │
│                                                     │
│   ┌────────────────┐    ┌─────────────────────┐    │
│   │  Flask API     │◄───┤  Tkinter GUI        │    │
│   │  (Waitress)    │    │  (Cashier's screen) │    │
│   │  Port 5000     │    │                     │    │
│   └────────┬───────┘    └─────────────────────┘    │
│            │                                        │
│            ▼                                        │
│   ┌────────────────┐                                │
│   │  SQLite DB     │                                │
│   │  (local file)  │                                │
│   └────────────────┘                                │
│                                                     │
│   Also serves the web app on the same port          │
│                                                     │
└────────────┬────────────────────────────────────────┘
             │
             │  LAN (WiFi)
             │
             ▼
      ┌──────────────┐
      │  Owner's     │
      │  phone / PC  │
      │  (browser)   │
      └──────────────┘
```

**The server runs as a Windows service.** It starts automatically on boot. The GUI is launched by the cashier when their shift begins.

**Why this architecture:**

- **No internet dependency.** Works if the WiFi goes down.
- **No cloud cost.** One-time hardware.
- **No SQLite data loss.** File lives on the store PC.
- **LAN-only access.** Owner can check reports from a phone, but nobody outside the store network can reach it.

**What this architecture does NOT support:**

- Remote access from outside the store's WiFi
- Multiple stores sharing one server
- Cloud backups without additional setup
- Native mobile apps

If any of those become requirements, the system needs to be redesigned. Do not try to force-fit them onto this architecture.

---

## Hardware Requirements

### Minimum
- Windows 10 or 11 (64-bit)
- 4 GB RAM
- 5 GB free disk space
- Wired or stable WiFi connection to the router
- Any modern processor (Intel i3 or equivalent is plenty)

### Recommended
- Windows 11
- 8 GB RAM
- SSD (much faster database operations)
- A UPS (uninterruptible power supply) — prevents data corruption on power loss
- A second monitor (web app on one, GUI on the other)

---

## Pre-Deployment Checklist

Run through this before you start. If you answer "no" to any of these, stop and address it first.

- [ ] You have physical access to the store PC
- [ ] You have Administrator rights on the store PC
- [ ] Python 3.11 or newer is installed on the store PC
- [ ] The store PC is connected to the store's WiFi/router
- [ ] You know the router's admin password (for DHCP reservation)
- [ ] You can find the store PC's local IP address (`ipconfig` in PowerShell)
- [ ] You have a USB drive for backups (recommended for cold storage)
- [ ] You have **changed the default `admin` password** (do this before going live)
- [ ] You have a backup copy of the project (GitHub, USB drive, or both)
- [ ] All tests pass on a dev machine (`python -m pytest backend\test -v`)

---

## Step 1: Prepare the Windows PC

### Create a dedicated Windows user

Running the server under a dedicated Windows account is safer than using the owner's personal account. If the account is ever compromised, it can be deleted without touching other users.

1. Open **Settings** → **Accounts** → **Family & other users**
2. Click **Add someone else to this PC**
3. Name: `pos-server`
4. Set a strong password (write it down somewhere safe, physically)
5. Type: **Standard user** (not Administrator — the server doesn't need admin rights)

Log in as `pos-server` for the remaining steps.

### Install Python

Download Python 3.12 from [python.org](https://www.python.org/downloads/).

**During install:**
- Check **"Add Python to PATH"** — critical
- Choose **Customize installation**
- Enable **"Install for all users"** if you want other accounts to run the app
- Disable **"Install launcher for all users"** (not needed)

Verify installation:

```powershell
python --version
# Should output: Python 3.12.x
```

### Install a PDF-capable browser (optional)

If you plan to print reports as PDF, install Chrome or Edge. Firefox works too. Not critical.

---

## Step 2: Install the Project

### Place the code

Copy the project to a stable location. **Do not leave it in a Downloads folder** — temporary folders get cleared.

Recommended path:

```
C:\POS\sari-sari-store-pos-main
```

If you're using Git:

```powershell
mkdir C:\POS
cd C:\POS
git clone <your-repo-url> sari-sari-store-pos-main
```

Or extract the ZIP to `C:\POS\`.

### Create the virtual environment

```powershell
cd C:\POS\sari-sari-store-pos-main
python -m venv venv
.\venv\Scripts\Activate.ps1
```

If activation is blocked:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

### Install dependencies

```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

This takes 2-5 minutes. Watch for errors — if any package fails to install, note the error and stop.

### Verify the install

```powershell
python -c "import flask, waitress, bcrypt, marshmallow; print('OK')"
```

Expected output: `OK`

---

## Step 3: Configure Production Environment

### Create the `.env` file

```powershell
Copy-Item .env.example .env
```

### Generate secret keys

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Run this **twice** — you need two different keys.

### Edit `.env`

Open `.env` in Notepad or VS Code. Fill in:

```env
APP_NAME= Saliga Sari-Sari Store POS
APP_ENV=production
DEBUG=False

HOST=0.0.0.0
PORT=5000

SECRET_KEY=<paste the first generated key>
JWT_SECRET_KEY=<paste the second generated key>

DB_TYPE=sqlite
DB_PATH=data/sari_sari_pos.db

# Replace 192.168.1.100 with this PC's actual local IP
CORS_ORIGINS=http://127.0.0.1:5000,http://192.168.1.100:5000

LOG_LEVEL=INFO
RATELIMIT_ENABLED=True
```

### Find the local IP

```powershell
ipconfig
```

Look for the "IPv4 Address" under your active adapter (WiFi or Ethernet). It will look like `192.168.1.xxx` or `10.0.0.xxx`.

Copy that into `CORS_ORIGINS`.

### Save and close `.env`

**Never commit `.env` to Git.** It contains the two secret keys that protect every session. If they leak, an attacker can forge login tokens.

The file is already in `.gitignore`, so `git status` won't show it.

---

## Step 4: Initialize the Database

With the venv still active:

```powershell
python run.py --init-db
```

Expected output:

```
============================================================
  INITIALIZING DATABASE
============================================================
[init_db] Database initialized successfully
  DB path: C:\POS\sari-sari-store-pos-main\data\sari_sari_pos.db
  Owner:   admin / admin123
  Cashier: cashier / cashier123
============================================================
```

The database now exists. Back it up immediately before making changes:

```powershell
python scripts\backup_db.py
```

Verify the backup:

```powershell
python scripts\backup_db.py list
```

---

## Step 5: Change Default Passwords

**Before anyone uses the system**, change the two default passwords.

1. Start the server temporarily:

```powershell
python run.py
```

2. Open a browser on the same PC and go to:
```
http://127.0.0.1:5000/login?role=owner
```

3. Log in as `admin` / `admin123`
4. Go to **Settings** → **Change My Password**
5. Enter the current password (`admin123`) and set a new strong password
6. Log out

7. Do the same for the cashier:
```
http://127.0.0.1:5000/login?role=cashier
```

8. Log in as `cashier` / `cashier123`, change the password
9. Log out

10. Stop the server (`Ctrl+C` in the terminal)

**Write the new passwords down and store them physically.** If the owner forgets the admin password, the only recovery path is to reset the database — which loses all sales history.

---

## Step 6: Install the Server as a Windows Service

We'll use **NSSM** (Non-Sucking Service Manager) to run the API as a background service that starts automatically on boot. Without this, you'd have to manually run `python run.py --serve` in a terminal every time the PC restarts.

### Download NSSM

1. Go to [nssm.cc/download](https://nssm.cc/download)
2. Download **NSSM 2.24** (or newer)
3. Extract `nssm-2.24.zip`
4. Copy `nssm-2.24\win64\nssm.exe` to `C:\Windows\System32\`

Verify:

```powershell
nssm version
```

### Install the service

**Open PowerShell as Administrator** (right-click → Run as administrator).

```powershell
$projectPath = "C:\POS\sari-sari-store-pos-main"
$pythonExe = "$projectPath\venv\Scripts\python.exe"
$runScript = "$projectPath\run.py"

nssm install SariSariPOS $pythonExe $runScript --serve
nssm set SariSariPOS AppDirectory $projectPath
nssm set SariSariPOS DisplayName "Sari-Sari Store POS Server"
nssm set SariSariPOS Description "Saliga Sari-Sari Store POS API server"
nssm set SariSariPOS Start SERVICE_AUTO_START
nssm set SariSariPOS AppStdout "$projectPath\logs\server_stdout.log"
nssm set SariSariPOS AppStderr "$projectPath\logs\server_stderr.log"
nssm set SariSariPOS AppRotateFiles 1
nssm set SariSariPOS AppRotateBytes 10485760
nssm set SariSariPOS AppRestartDelay 5000
```

### Start the service

```powershell
nssm start SariSariPOS
```

### Verify it's running

```powershell
nssm status SariSariPOS
```

Expected: `SERVICE_RUNNING`

```powershell
curl.exe http://127.0.0.1:5000/health
```

Expected:
```json
{"status":"healthy","app":"...","environment":"production","database":"connected"}
```

### What just happened

The API now runs as a Windows service. It starts on every boot automatically. If it crashes, NSSM restarts it after 5 seconds. Its stdout and stderr go to `logs/`.

### Uninstall (if needed)

```powershell
nssm stop SariSariPOS
nssm remove SariSariPOS confirm
```

---

## Step 7: Create the GUI Launcher

The cashier needs one double-click to start the register.

Create `C:\POS\Start POS.bat`:

```batch
@echo off
title POS - Saliga Sari-Sari Store
cd /d "C:\POS\sari-sari-store-pos-main"
call venv\Scripts\activate.bat
python run.py --gui
pause
```

Create a desktop shortcut:

1. Right-click `Start POS.bat`
2. Send to → Desktop (create shortcut)
3. Rename the desktop shortcut to **POS**

Set a custom icon (optional):

1. Right-click the shortcut → Properties → Change Icon
2. Point to any `.ico` file, or use `C:\Windows\System32\shell32.dll` and pick a store-ish icon

### Test it

Double-click the desktop **POS** shortcut. The GUI should launch and connect to the API (which is running as a service).

Log in as `cashier` with the new password. Verify products load.

If products don't load, the GUI can't reach the API. Check:
- The service is running: `nssm status SariSariPOS`
- The API responds: `curl.exe http://127.0.0.1:5000/health`
- The GUI's `api_url` is set correctly (default `http://127.0.0.1:5000/api/v1`)

---

## Step 8: Set Up Automated Backups

Backups must run automatically. Manual backups are backups that don't happen.

### Open Task Scheduler

Press `Win+R`, type `taskschd.msc`, press Enter.

### Create the task

1. Right panel → **Create Task** (not Basic Task — we need more options)
2. **General** tab:
   - Name: `Sari-Sari POS Daily Backup`
   - Description: `Creates a timestamped backup of the POS database`
   - Run whether user is logged on or not
   - Run with highest privileges
   - Configure for: Windows 10 / Windows 11

3. **Triggers** tab → New:
   - Begin the task: On a schedule
   - Daily
   - Start: 11:00 PM (end of business day)
   - Recur every: 1 day
   - Enabled: ✓

4. **Actions** tab → New:
   - Action: Start a program
   - Program/script: `C:\POS\sari-sari-store-pos-main\venv\Scripts\python.exe`
   - Add arguments: `scripts\backup_db.py`
   - Start in: `C:\POS\sari-sari-store-pos-main`

5. **Conditions** tab:
   - Uncheck "Start the task only if the computer is on AC power" (store PC is always plugged in)
   - Check "Wake the computer to run this task" (optional)

6. **Settings** tab:
   - Allow task to be run on demand
   - Stop the task if it runs longer than: 10 minutes
   - If the running task does not end when requested: Stop the existing instance
   - If the task is already running, then the following rule applies: Do not start a new instance

7. Click **OK**. Enter the `pos-server` account password when prompted.

### Test the backup task

Right-click the task → **Run**. Then verify:

```powershell
python scripts\backup_db.py list
```

You should see a new `.db` file with today's timestamp.

### Copy backups to USB weekly

**Critical:** if the store PC's hard drive dies, local backups die with it. Every week, copy `data\backups\` to a USB drive. Store the USB drive off-site (owner's home, safe, etc.).

Add this to the maintenance schedule.

---

## Step 9: Configure the Firewall

So the owner's phone can reach the web app on the store's WiFi.

### Add the rule

**Open PowerShell as Administrator:**

```powershell
New-NetFirewallRule `
    -DisplayName "Sari-Sari POS Server" `
    -Direction Inbound `
    -Protocol TCP `
    -LocalPort 5000 `
    -Action Allow `
    -Profile Private
```

The `-Profile Private` means only devices on the same private network can reach it. Public WiFi (coffee shops, airports) cannot.

### Verify

```powershell
Get-NetFirewallRule -DisplayName "Sari-Sari POS Server"
```

Expected: `Enabled: True`, `Direction: Inbound`

### Test from the owner's phone

1. Connect the phone to the store's WiFi
2. Open a browser
3. Go to `http://<store-PC-IP>:5000`
4. The site should load

Replace `<store-PC-IP>` with the IP from Step 10.

If it fails to load:
- Phone is on a different WiFi network
- Firewall rule was applied to the wrong profile
- Store PC's IP changed (see Step 10)

---

## Step 10: Set Up a Static IP

The store PC's IP must stay the same so the owner's phone has a stable URL.

### Find the current IP

```powershell
ipconfig
```

Note the IPv4 address, subnet mask, and default gateway.

### Option A: Static IP on the PC

1. Settings → Network & Internet → Properties of the active adapter
2. Scroll to IP settings → Edit → Manual → IPv4
3. Enter:
   - IP address: `192.168.1.100` (pick something outside the DHCP range)
   - Subnet mask: `255.255.255.0`
   - Gateway: `192.168.1.1` (from `ipconfig`)
   - Preferred DNS: `8.8.8.8`
   - Alternate DNS: `1.1.1.1`
4. Save

**Risk:** if the chosen IP is inside the router's DHCP range, another device could take it. Ask the owner's router admin page for the DHCP range and pick an IP outside it.

### Option B: DHCP reservation (preferred)

1. Open the router admin page (usually `http://192.168.1.1`)
2. Log in (username/password on the router's sticker if never changed)
3. Find **DHCP Reservation** or **Static Lease**
4. Add an entry for the store PC's MAC address, assigning it a fixed IP
5. Save

This way, the router always gives the store PC the same IP.

### Verify

```powershell
# Unplug and replug network, or restart
ipconfig

# IP should be the one you set
```

Test the API from another device on the same network:

```
http://192.168.1.100:5000/api
```

Expected: JSON describing the API.

---

## Verifying the Deployment

Run through this checklist. Every box must be checked.

### Automated
- [ ] `nssm status SariSariPOS` → `SERVICE_RUNNING`
- [ ] `curl.exe http://127.0.0.1:5000/health` → `{"status":"healthy",...}`
- [ ] `python -m pytest backend\test -v` → all tests pass
- [ ] `python scripts\backup_db.py list` → at least one backup exists

### Web
- [ ] Browser at `http://127.0.0.1:5000` loads home page
- [ ] Login as owner works with new password
- [ ] Dashboard loads with real numbers
- [ ] Products page loads
- [ ] POS works — make a test sale
- [ ] All Sales page shows the test sale
- [ ] Reports page generates a report
- [ ] Settings page loads and saves
- [ ] Categories page loads and can add/delete
- [ ] Logout works
- [ ] Back button after logout does NOT show authenticated pages

### GUI
- [ ] Desktop POS shortcut opens the GUI
- [ ] Login as cashier works
- [ ] Products load in the products grid
- [ ] POS: add product to cart, checkout with cash, sale recorded
- [ ] POS: barcode scanning works (USB scanner)
- [ ] Products: add a test product with category dropdown
- [ ] Sales History loads

### Remote (owner's phone)
- [ ] Browser on phone at `http://<store-PC-IP>:5000` loads home page
- [ ] Owner can log in from the phone
- [ ] Reports generate on the phone

### Cross-client sync
- [ ] Owner adds a category on the phone
- [ ] GUI's Add Product dialog shows the new category (after reopening)
- [ ] Owner makes a sale on the phone
- [ ] GUI's All Sales/Sales History shows the new sale

If any box fails, stop and fix. Don't proceed until every check passes.

---

## Day-to-Day Operations

### Morning

1. Turn on the store PC
2. Wait 30 seconds for the service and Windows to finish booting
3. Double-click the desktop POS shortcut
4. Log in as cashier
5. Verify the product list loads
6. Start selling

### During the day

- Sales record in real time
- Stock updates immediately
- Backups are not needed during the day

### Evening

1. Close the GUI when the shift ends
2. Verify last night's backup ran: `python scripts\backup_db.py list`
3. Optional: check the daily report on the owner's phone

### Weekly

- Copy `data\backups\` to a USB drive
- Store the USB drive off-site (owner's home, safe, etc.)
- Check Windows updates and install during closed hours

### Monthly

- Rotate the admin password
- Review the audit log for anything suspicious
- Run a restore test in a test folder (see Emergency Procedures)

---

## Maintenance Schedule

| Frequency | Task |
|---|---|
| Daily | Verify backup ran, close GUI at end of shift |
| Weekly | Copy backups to USB, store off-site |
| Weekly | Review low-stock alerts, restock as needed |
| Monthly | Rotate admin password |
| Monthly | Review audit log |
| Monthly | Run a restore test in a test folder |
| Quarterly | Apply Windows updates |
| Quarterly | Review the CHANGELOG and consider applying updates |
| Yearly | Replace the UPS battery |
| Yearly | Archive old sales (over 2 years) if performance degrades |

---

## Troubleshooting

### Server won't start

```powershell
nssm status SariSariPOS
```

If not `SERVICE_RUNNING`:

```powershell
nssm restart SariSariPOS
```

Check the log:

```powershell
Get-Content "C:\POS\sari-sari-store-pos-main\logs\server_stderr.log" -Tail 50
```

Common causes:
- Port 5000 already in use by another program
- Database file locked (another process opened it)
- Python venv broken (recreate it)

### Server runs but the API returns 500 errors

Check `logs\app.log`:

```powershell
Get-Content "C:\POS\sari-sari-store-pos-main\logs\app.log" -Tail 100
```

If the log mentions a missing table, re-run migrations or restore from backup.

### GUI can't connect

1. Check the service is running (`nssm status`)
2. Test the API directly: `curl.exe http://127.0.0.1:5000/health`
3. Check the GUI's server URL (default `http://127.0.0.1:5000/api/v1`)
4. Restart the GUI

### Owner can't access from phone

1. Is the phone on the same WiFi as the store PC? (Yes/No — check the WiFi name)
2. Is the store PC's firewall rule active?
3. Is the store PC's IP the one the owner is using? (`ipconfig`)
4. Try from another device (a laptop on the same WiFi)

### "Session invalid" errors after using the site for a while

Token expired (8-hour lifetime). Log in again.

### Database file is corrupt

1. Stop the service: `nssm stop SariSariPOS`
2. Restore the most recent backup (see Emergency Procedures)
3. Start the service: `nssm start SariSariPOS`

### Disk full

Delete old logs:
```powershell
Get-ChildItem "C:\POS\sari-sari-store-pos-main\logs" -Filter "*.log.*" | Remove-Item
```

Or check backup folder:
```powershell
Get-ChildItem "C:\POS\sari-sari-store-pos-main\data\backups" | Sort-Object LastWriteTime | Select-Object -First 10
```

Delete older backups only after verifying weekly USB copies exist.

### Password reset needed for admin

If the admin password is lost:

1. Stop the service
2. Open the database with [DB Browser for SQLite](https://sqlitebrowser.org/)
3. Find the `users` table
4. Delete the row where `username = 'admin'`
5. Update `scripts\seed_default_user.py` (or write a small script) to re-create admin with a fresh password
6. Restart the service

**This is why you store passwords physically.** Avoid needing this procedure.

---

## Emergency Procedures

### Restore from backup

**Only do this if the database is unusable.** Restoring overwrites all current data.

1. **Stop the service:**
   ```powershell
   nssm stop SariSariPOS
   ```

2. **Make a safety copy of the current DB:**
   ```powershell
   cd C:\POS\sari-sari-store-pos-main
   Copy-Item "data\sari_sari_pos.db" "data\sari_sari_pos.db.broken_$(Get-Date -Format 'yyyyMMdd_HHmmss')"
   ```

3. **List available backups:**
   ```powershell
   python scripts\backup_db.py list
   ```

4. **Restore:**
   ```powershell
   python scripts\backup_db.py restore sari_sari_pos_YYYYMMDD_HHMMSS.db
   ```

5. **Verify the restored DB:**
   ```powershell
   python scripts\backup_db.py list
   # The restored DB should be in place
   ```

6. **Start the service:**
   ```powershell
   nssm start SariSariPOS
   ```

7. **Verify:**
   - Health endpoint responds
   - Log in as admin
   - Check recent sales look correct

8. **If the restore was wrong**, the safety copy from step 2 can be moved back.

### Restore test (do monthly)

Do not skip this. A backup that can't be restored is not a backup.

1. Copy a backup file to a test folder
2. Copy the entire project to a test location
3. In the test copy, restore the backup
4. Verify:
   - Server starts
   - Login works
   - Data looks correct
5. Delete the test copy

Do this on a machine that is NOT the production server, so you don't risk overwriting real data.

### Power loss

If the PC loses power while the server is running:

1. When power returns, the server auto-starts (Windows service)
2. Check `logs\app.log` for the last operation before the crash
3. Verify recent sales are present in the web app
4. If data is missing, restore the previous night's backup

**A UPS is highly recommended** to prevent this scenario entirely.

### Lost admin password

See "Password reset needed for admin" above.

### Database file deleted

1. Stop the service
2. Restore the most recent backup
3. If no backups exist, reinitialize the database (loses all data)

**This is why you keep USB backups off-site.**

---

## Appendix: Uninstalling

### Stop and remove the service

```powershell
# As Administrator
nssm stop SariSariPOS
nssm remove SariSariPOS confirm
```

### Delete the project

```powershell
Remove-Item "C:\POS\sari-sari-store-pos-main" -Recurse -Force
```

### Remove the firewall rule

```powershell
Remove-NetFirewallRule -DisplayName "Sari-Sari POS Server"
```

### Remove the scheduled task

Task Scheduler → Find "Sari-Sari POS Daily Backup" → Delete

### What remains

- Windows user `pos-server` (remove manually if not needed)
- Python installation (remove via Programs & Features)
- NSSM in `C:\Windows\System32\nssm.exe` (safe to delete)

---

## Summary — What To Do

1. **Read this document fully** before starting
2. **Run the pre-deployment checklist**
3. **Do steps 1-10 in order**
4. **Run the verification checklist** — every box checked
5. **Do a restore test** before going live
6. **Write the admin password on paper** and store it physically
7. **Set a calendar reminder** for the monthly and weekly maintenance tasks

Once done, the system runs unattended for months. The only ongoing work is the weekly USB backup copy and the monthly restore test.
