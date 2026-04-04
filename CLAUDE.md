# ProyControl UTP

## Context
Centralized projector control system for UTP (Universidad Tecnológica del Perú), Arequipa campus. Controls projectors across 3 campuses (Tacna y Arica, Parra 1, Parra 2) from a unified web interface using PJLink protocol.

## Problem statement
- Projectors on DHCP change IP → control stops working
- Duplicate IPs → conflicts affecting multiple classrooms
- Physical visit to each classroom required to reconfigure → time waste
- Solution: scanner identifies projectors by MAC, IP updates automatically

## Architecture
```
Admin PC (VLAN 30) ──→ Local web server (Flask + SQLite)
                              ↕
Teacher PCs (VLAN 30) ──→ Simple view (power on/off only)
                              ↕
                      Periodic scanner
                              ↕
                    Projectors (VLAN 71) ← PJLink TCP:4352
```

## Network
- VLAN 30 (teacher PCs + admin PC): has access to VLAN 71 via ACL
- VLAN 71 (projectors): 10.225.71.x (TyA, Parra 1) / 10.235.71.x (Parra 2)
- Gateway: 10.225.71.1 | Netmask: 255.255.255.0 | DNS: 10.225.31.3
- Server runs on admin PC with VLAN 30 port

## Validated projectors
| Brand | Model | Port | Auth |
|-------|-------|------|------|
| NEC | ME403 Series | 4352 | No password |
| Epson | PowerLite 119W | 4352 | No password |
| ViewSonic | PG707X | 4352 | No password |

All respond with PJLINK 0 (no authentication).

### Required projector configuration
- NEC: "Modo de espera" → "Red en espera"
- Epson: PJLink → On, Control básico → On, reboot after changes
- ViewSonic: Disable web password

## PJLink protocol
```
Power on:      %1POWR 1\r    → %1POWR=OK
Power off:     %1POWR 0\r    → %1POWR=OK
Status:        %1POWR ?\r    → %1POWR=0 (off) | =1 (on) | =2 (cooling) | =3 (warming)
Name:          %1NAME ?\r    → %1NAME=PG707X
Manufacturer:  %1INF1 ?\r    → %1INF1=ViewSonic
Model:         %1INF2 ?\r    → %1INF2=Data Projector
Input:         %1INPT ?\r    → %1INPT=31 (HDMI)

Error codes:
  ERR1 = undefined command
  ERR2 = out of parameter
  ERR3 = unavailable time (projector busy/transitioning)
  ERR4 = projector/display failure
  ERRA = authentication error
```
Flow: TCP connect :4352 → read greeting "PJLINK 0\r" → send command → read response → close

## MAC detection
PJLink does not return MAC. After a PJLink connection, the MAC is cached in the OS ARP table.
- Windows: `arp -a` → parse output for target IP
- Python: subprocess + regex parse arp output

## Tech stack
- **Language**: Python 3.10+
- **Backend**: Flask (lightweight, right-sized for this project — Django would be overkill)
- **Database**: SQLite (single .db file, no server needed)
- **Frontend**: HTML5 + CSS3 + vanilla JS (no heavy frameworks)
- **Protocol**: PJLink over raw TCP sockets (no external libraries)
- **Scanning**: socket connect to port 4352 across IP range
- **Environment**: venv (always use virtual environment)

### Why Flask over Django
This is a focused API + simple web UI, not a large-scale web application. Flask gives us exactly what we need (routing, templates, JSON responses) without the overhead of Django's ORM, admin panel, migrations system, auth framework, etc. Professional choice = right tool for the job.

## Project structure
```
proycontrol/
├── CLAUDE.md
├── requirements.txt        # Flask + any pip dependencies
├── .gitignore
├── venv/                   # Virtual environment (not committed)
├── app.py                  # Flask app entry point
├── config.py               # App configuration (subnets, scan interval, etc.)
├── models/
│   ├── __init__.py
│   └── database.py         # SQLite setup + CRUD operations
├── services/
│   ├── __init__.py
│   ├── pjlink.py           # PJLink protocol module
│   ├── scanner.py          # Network scanner (discover + ARP MAC)
│   └── scheduler.py        # Periodic scan scheduler
├── routes/
│   ├── __init__.py
│   ├── api.py              # REST API endpoints
│   ├── admin.py            # Admin panel routes
│   └── teacher.py          # Teacher control routes
├── templates/
│   ├── base.html           # Base template with shared layout
│   ├── admin/
│   │   ├── dashboard.html  # Main admin panel
│   │   └── projector.html  # Single projector detail
│   └── teacher/
│       └── control.html    # Simple on/off interface
├── static/
│   ├── css/
│   │   └── style.css       # Shared styles
│   └── js/
│       ├── admin.js        # Admin panel logic
│       └── teacher.js      # Teacher control logic
└── tests/
    ├── __init__.py
    ├── test_pjlink.py      # PJLink module tests
    └── test_scanner.py     # Scanner tests
```

## Database schema
```sql
CREATE TABLE campuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,              -- 'Tacna y Arica', 'Parra 1', 'Parra 2'
    subnet TEXT NOT NULL             -- '10.225.71', '10.235.71'
);

CREATE TABLE classrooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    campus_id INTEGER NOT NULL,
    number TEXT NOT NULL,            -- '301', '302', 'A101'
    display_name TEXT NOT NULL,      -- 'Aula 301'
    FOREIGN KEY (campus_id) REFERENCES campuses(id)
);

CREATE TABLE projectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    classroom_id INTEGER,            -- NULL if unassigned
    mac_address TEXT UNIQUE,         -- 'AA:BB:CC:DD:EE:FF'
    current_ip TEXT,                 -- '10.225.71.52'
    brand TEXT,                      -- 'NEC', 'Epson', 'ViewSonic'
    model TEXT,                      -- 'ME403 Series'
    pjlink_name TEXT,                -- 'PJ-1Z00383LD'
    last_seen TIMESTAMP,            -- Last successful scan
    status TEXT DEFAULT 'unknown',   -- 'on', 'off', 'cooling', 'warming', 'unknown'
    FOREIGN KEY (classroom_id) REFERENCES classrooms(id)
);

CREATE TABLE scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip TEXT NOT NULL,
    mac_address TEXT,
    event TEXT NOT NULL              -- 'discovered', 'ip_changed', 'offline', 'new_mac'
);
```

## API endpoints
```
# Admin endpoints
GET    /api/projectors              → List all with status
GET    /api/projectors/:id          → Single projector detail
POST   /api/projectors/:id/power-on → Power on
POST   /api/projectors/:id/power-off→ Power off
GET    /api/projectors/:id/status   → Current power status
POST   /api/projectors/:id/assign   → Assign projector to classroom
PUT    /api/projectors/:id/mac      → Update MAC (for rotation)
POST   /api/scan                    → Trigger manual scan
GET    /api/scan/log                → Scan history / events

# Teacher endpoints
GET    /api/classroom/:number/info    → Classroom projector info
POST   /api/classroom/:number/power-on  → Power on by classroom
POST   /api/classroom/:number/power-off → Power off by classroom

# Web routes
GET    /admin                       → Admin dashboard
GET    /admin/projector/:id         → Projector detail page
GET    /control/:classroom_number   → Teacher simple control page
```

## Development guidelines

### Language conventions
- **Code** (variables, functions, classes, files): English
- **Comments**: Spanish (for internal team readability)
- **UI text** (labels, buttons, messages): Spanish (end users are Spanish speakers)
- **Git commits**: English

### Naming conventions
```python
# Functions: snake_case, descriptive verbs
def get_projector_status(ip: str) -> dict:
def scan_subnet(subnet: str) -> list:
def get_mac_from_arp(ip: str) -> str:

# Classes: PascalCase
class ProjectorScanner:
class PJLinkConnection:

# Constants: UPPER_SNAKE_CASE
PJLINK_PORT = 4352
SCAN_INTERVAL_SECONDS = 300
DEFAULT_TIMEOUT = 5

# Database columns: snake_case
# API endpoints: kebab-case (/power-on, /power-off)
# HTML ids/classes: kebab-case
```

### Python best practices
- Type hints on all function signatures
- Docstrings on all public functions (Spanish)
- f-strings for string formatting
- Context managers for sockets and DB connections
- Logging module instead of print statements
- Exception handling with specific exceptions
- Virtual environment (venv) always

### Error handling
```python
# PJLink connections WILL fail (projector off, network issue, timeout)
# Always handle gracefully — never crash the server
try:
    status = get_projector_status(ip)
except ConnectionTimeout:
    status = {"status": "unreachable", "message": "Projector not responding"}
except ConnectionRefused:
    status = {"status": "offline", "message": "Port closed"}
```

### Frontend guidelines
- Mobile-responsive (admin may use from phone)
- Auto-refresh projector status every 30 seconds on admin panel
- Teacher view: maximum 2 buttons visible, large touch targets
- Visual feedback on every action (loading spinner, success/error message)
- Color coding: green=on, red=off, yellow=transitioning, gray=unknown

### Security considerations
- Admin panel: basic auth (username/password)
- Teacher view: no auth needed (only on/off, no sensitive data)
- No external internet access required
- All traffic stays within UTP internal network

## Setup instructions
```bash
# Create project directory
mkdir proycontrol && cd proycontrol

# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run
python app.py
```

## Development order
1. `services/pjlink.py` — PJLink protocol module
2. `services/scanner.py` — Network scanner with ARP MAC detection
3. `models/database.py` — SQLite setup and CRUD
4. `config.py` — Configuration management
5. `app.py` + `routes/api.py` — API endpoints
6. `routes/admin.py` + `templates/admin/` — Admin panel
7. `routes/teacher.py` + `templates/teacher/` — Teacher control
8. `services/scheduler.py` — Automatic periodic scanning
9. `tests/` — Unit tests

## Pending (does not block development)
- DHCP Snooping + DAI on VLAN 71 (prevents duplicate IPs)
- Configured on HPE Aruba access switches via Aruba Central
- Does not touch core or change network topology
- Recommended by HPE Aruba in their official hardening guide
