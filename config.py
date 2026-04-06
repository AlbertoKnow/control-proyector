"""
Configuración central de ProyControl UTP.
Todas las constantes y parámetros ajustables del sistema.
"""

# --- PJLink ---
PJLINK_PORT: int = 4352
DEFAULT_TIMEOUT: int = 5          # segundos para conexiones PJLink
SCAN_TIMEOUT: int = 2             # segundos para detección rápida en escaneo

# --- Escaneo periódico ---
SCAN_INTERVAL_SECONDS: int = 1800  # cada 30 minutos
AUTO_SCAN_ON_STARTUP: bool = True   # escaneo automático activado

# --- Red / subredes de proyectores ---
SUBNETS: list[str] = [
    "10.225.71",   # Tacna y Arica + Parra 1
    "10.235.71",   # Parra 2
]

# Rango de hosts a escanear dentro de cada subred (1–254)
SCAN_HOST_START: int = 1
SCAN_HOST_END: int = 254

# --- Base de datos ---
DATABASE_PATH: str = "proycontrol.db"

# --- Flask ---
SECRET_KEY: str = "cambia-esto-en-produccion"
DEBUG: bool = True

# Credenciales panel admin (basic auth)
ADMIN_USERNAME: str = "admin"
ADMIN_PASSWORD: str = "utp2024"
