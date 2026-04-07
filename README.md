# ProyControl UTP

Sistema centralizado de control de proyectores para la **Universidad Tecnológica del Perú — sede Arequipa**. Permite encender y apagar proyectores de las tres sedes desde una interfaz web, resolviendo el problema del cambio automático de IPs en red DHCP mediante identificación por número de serie (PJLink).

## Problema que resuelve

| Problema | Solución |
|----------|----------|
| Proyectores en DHCP cambian de IP | Scanner identifica por número de serie, actualiza IP automáticamente |
| IPs duplicadas generan conflictos | UNIQUE por `pjlink_name`; compatible con DHCP Snooping + DAI |
| Visita física para reconfigurar | Control remoto vía protocolo PJLink (TCP 4352) |
| Docente necesita saber la IP | URL fija por número de aula — nunca cambia |

## Arquitectura

```
Admin PC (VLAN 30) ──→ Servidor Flask + SQLite
                              ↕
PC Docente (VLAN 30) ──→ Vista simple (encender/apagar)
                              ↕
                      Scanner periódico (cada 30 min)
                              ↕
                    Proyectores (VLAN 71) ← PJLink TCP:4352
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
# Clonar repositorio
git clone https://github.com/AlbertoKnow/control-proyector.git
cd control-proyector

# Crear entorno virtual
python -m venv venv

# Activar (Windows)
venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt

# Iniciar servidor
python app.py
```

## Uso

### Panel de administración
```
http://<IP-servidor>:5000/admin
```
- Usuario: `admin` / Contraseña: `utp2024` *(cambiar en `config.py`)*
- Lista todos los proyectores por campus con estado en tiempo real
- Escaneo manual de red
- Asignación de proyectores a aulas

### Vista del docente
```
http://<IP-servidor>:5000/control/<número-aula>
```
Ejemplo: `http://10.225.30.110:5000/control/C0305`
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
│   └── teacher.py          # Vista del docente
├── templates/
│   ├── base.html
│   ├── admin/              # Dashboard y detalle de proyector
│   └── teacher/            # Control simple encender/apagar
├── static/
│   ├── css/                # Estilos compartidos + vista docente
│   └── js/                 # Lógica admin + docente
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

- **VLAN 30** (PCs docentes + admin): acceso a VLAN 71 vía ACL
- **VLAN 71** (proyectores): `10.225.71.x` (TyA, Parra 1) / `10.235.71.x` (Parra 2)
- Puerto TCP 4352 abierto desde VLAN 30 hacia VLAN 71
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

## Pendiente

- [ ] Configurar como servicio de Windows (inicio automático)
- [ ] Abrir puerto 5000 en firewall de Windows
- [ ] DHCP Snooping + DAI en switches HPE Aruba de VLAN 71
- [ ] Integrar binding table DHCP para poblar MAC addresses automáticamente
- [ ] Agregar sedes Parra 2 (`10.235.71.x`) una vez disponibles
