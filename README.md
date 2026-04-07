# ProyControl

Sistema centralizado de control de proyectores vía red. Permite encender y apagar proyectores desde una interfaz web, resolviendo el problema del cambio automático de IPs en red DHCP mediante identificación por número de serie (PJLink).

## Problema que resuelve

| Problema | Solución |
|----------|----------|
| Proyectores en DHCP cambian de IP | Scanner identifica por número de serie, actualiza IP automáticamente |
| IPs duplicadas generan conflictos | UNIQUE por `pjlink_name`; compatible con DHCP Snooping + DAI |
| Visita física para reconfigurar | Control remoto vía protocolo PJLink (TCP 4352) |
| Usuario necesita saber la IP | URL fija por número de aula — nunca cambia |

## Arquitectura

```
Admin PC ──→ Servidor Flask + SQLite
                    ↕
PC Usuario ──→ Vista simple (encender/apagar)
                    ↕
            Scanner periódico (cada 30 min)
                    ↕
          Proyectores ← PJLink TCP:4352
```

## Proyectores validados

| Marca | Modelo | Autenticación |
|-------|--------|---------------|
| Sharp NEC | ME403 Series | Sin contraseña |
| Sharp NEC | MC423 Series | Sin contraseña |
| Epson | PowerLite 119W / X39 | Sin contraseña |
| ViewSonic | PG707X | Sin contraseña |

## Stack tecnológico

- **Backend:** Python 3.10+ / Flask
- **Base de datos:** SQLite
- **Frontend:** HTML5 + CSS3 + JavaScript vanilla
- **Protocolo:** PJLink Clase 1 sobre TCP sin autenticación
- **Identificación:** `pjlink_name` (número de serie) como identificador único

## Instalación

```bash
git clone https://github.com/AlbertoKnow/control-proyector.git
cd control-proyector

python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt
python app.py
```

## Uso

### Panel de administración
```
http://<IP-servidor>:5000/admin
```
- Lista todos los proyectores por campus con estado en tiempo real
- Escaneo manual de red
- Asignación de proyectores a aulas

### Vista de control
```
http://<IP-servidor>:5000/control/<número-aula>
```
- Sin login requerido
- Solo dos botones: Encender / Apagar
- La URL nunca cambia aunque el proyector cambie de IP

## Estructura del proyecto

```
control-proyector/
├── app.py                  # Punto de entrada Flask
├── config.py               # Configuración (subredes, intervalos, credenciales)
├── models/
│   └── database.py         # SQLite — esquema y operaciones CRUD
├── services/
│   ├── pjlink.py           # Protocolo PJLink sobre TCP
│   ├── scanner.py          # Escáner de red con detección por número de serie
│   └── scheduler.py        # Escaneo periódico automático en hilo daemon
├── routes/
│   ├── api.py              # REST API (12 endpoints)
│   ├── admin.py            # Panel de administración
│   └── teacher.py          # Vista de control
├── templates/
│   ├── base.html
│   ├── admin/              # Dashboard y detalle de proyector
│   └── teacher/            # Control simple encender/apagar
├── static/
│   ├── css/                # Estilos compartidos + vista de control
│   └── js/                 # Lógica admin + control
└── tests/
    ├── test_pjlink.py      # 33 tests del módulo PJLink
    └── test_scanner.py     # 17 tests del módulo scanner
```

## API REST

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/projectors` | Lista todos los proyectores |
| GET | `/api/projectors/:id/status` | Estado en tiempo real vía PJLink |
| POST | `/api/projectors/:id/power-on` | Encender |
| POST | `/api/projectors/:id/power-off` | Apagar |
| POST | `/api/projectors/:id/assign` | Asignar a aula |
| PUT | `/api/projectors/:id/mac` | Actualizar MAC address |
| POST | `/api/scan` | Escaneo manual de red |
| GET | `/api/scan/log` | Historial de eventos |
| GET | `/api/classroom/:number/info` | Info del aula |
| POST | `/api/classroom/:number/power-on` | Encender por número de aula |
| POST | `/api/classroom/:number/power-off` | Apagar por número de aula |
| GET | `/api/scheduler/status` | Estado del scanner automático |

## Configuración de red requerida

- Puerto TCP 4352 abierto desde la red de control hacia los proyectores
- Puerto 5000 abierto en firewall de la PC servidor

## Configuración requerida en proyectores

| Marca | Configuración |
|-------|--------------|
| NEC | Modo de espera → **Red en espera** |
| Epson | PJLink → On, Control básico → On, reiniciar |
| ViewSonic | Deshabilitar contraseña web |

## Tests

```bash
python -m unittest discover -v tests
# 50 tests — PJLink protocol + network scanner
```
