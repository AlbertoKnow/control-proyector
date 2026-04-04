"""
Módulo de base de datos SQLite para ProyControl.
Gestiona la inicialización del esquema y todas las operaciones CRUD.
"""

import sqlite3
import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from config import DATABASE_PATH

logger = logging.getLogger(__name__)

# --- Schema SQL ---

_SCHEMA = """
CREATE TABLE IF NOT EXISTS campuses (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL,
    subnet  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS classrooms (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    campus_id    INTEGER NOT NULL,
    number       TEXT NOT NULL,
    display_name TEXT NOT NULL,
    FOREIGN KEY (campus_id) REFERENCES campuses(id)
);

CREATE TABLE IF NOT EXISTS projectors (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    classroom_id INTEGER,
    mac_address  TEXT UNIQUE,
    current_ip   TEXT,
    brand        TEXT,
    model        TEXT,
    pjlink_name  TEXT,
    last_seen    TIMESTAMP,
    status       TEXT DEFAULT 'unknown',
    FOREIGN KEY (classroom_id) REFERENCES classrooms(id)
);

CREATE TABLE IF NOT EXISTS scan_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ip          TEXT NOT NULL,
    mac_address TEXT,
    event       TEXT NOT NULL
);
"""

_SEED = """
INSERT OR IGNORE INTO campuses (id, name, subnet) VALUES
    (1, 'Tacna y Arica', '10.225.71'),
    (2, 'Parra 1',       '10.225.71'),
    (3, 'Parra 2',       '10.235.71');
"""


# --- Conexión ---

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager que abre y cierra la conexión a SQLite.
    Hace commit automático al salir sin error; rollback si hay excepción.

    Uso:
        with get_db() as conn:
            conn.execute(...)
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row          # acceso por nombre de columna
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Crea las tablas si no existen e inserta los campus por defecto.
    Se puede llamar varias veces sin efecto secundario.
    """
    with get_db() as conn:
        conn.executescript(_SCHEMA)
        conn.executescript(_SEED)
    logger.info("Base de datos inicializada en '%s'", DATABASE_PATH)


# --- Campus ---

def get_all_campuses() -> list[sqlite3.Row]:
    """Retorna todos los campus registrados."""
    with get_db() as conn:
        return conn.execute("SELECT * FROM campuses ORDER BY id").fetchall()


def get_campus(campus_id: int) -> sqlite3.Row | None:
    """Retorna un campus por ID o None si no existe."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM campuses WHERE id = ?", (campus_id,)
        ).fetchone()


# --- Aulas ---

def get_classrooms(campus_id: int | None = None) -> list[sqlite3.Row]:
    """
    Retorna aulas, opcionalmente filtradas por campus.

    Args:
        campus_id: Si se indica, filtra por ese campus.
    """
    with get_db() as conn:
        if campus_id is not None:
            return conn.execute(
                "SELECT * FROM classrooms WHERE campus_id = ? ORDER BY number",
                (campus_id,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM classrooms ORDER BY campus_id, number"
        ).fetchall()


def get_classroom_by_number(number: str) -> sqlite3.Row | None:
    """Busca un aula por su número (ej: '301'). Retorna None si no existe."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM classrooms WHERE number = ?", (number,)
        ).fetchone()


def create_classroom(campus_id: int, number: str, display_name: str) -> int:
    """
    Crea una nueva aula.

    Returns:
        ID del aula creada.
    """
    with get_db() as conn:
        cursor = conn.execute(
            "INSERT INTO classrooms (campus_id, number, display_name) VALUES (?, ?, ?)",
            (campus_id, number, display_name),
        )
        logger.info("Aula creada: %s (%s)", display_name, number)
        return cursor.lastrowid


# --- Proyectores ---

def get_all_projectors() -> list[sqlite3.Row]:
    """
    Retorna todos los proyectores con datos de aula y campus adjuntos.
    """
    with get_db() as conn:
        return conn.execute("""
            SELECT
                p.*,
                c.number    AS classroom_number,
                c.display_name AS classroom_name,
                ca.name     AS campus_name
            FROM projectors p
            LEFT JOIN classrooms c  ON p.classroom_id = c.id
            LEFT JOIN campuses   ca ON c.campus_id    = ca.id
            ORDER BY ca.name, c.number
        """).fetchall()


def get_projector(projector_id: int) -> sqlite3.Row | None:
    """Retorna un proyector por ID o None si no existe."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM projectors WHERE id = ?", (projector_id,)
        ).fetchone()


def get_projector_by_mac(mac_address: str) -> sqlite3.Row | None:
    """Busca un proyector por MAC address (case-insensitive)."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM projectors WHERE UPPER(mac_address) = UPPER(?)",
            (mac_address,),
        ).fetchone()


def get_projector_by_classroom(classroom_id: int) -> sqlite3.Row | None:
    """Retorna el proyector asignado a un aula, o None si no hay ninguno."""
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM projectors WHERE classroom_id = ?", (classroom_id,)
        ).fetchone()


def create_projector(
    mac_address: str | None,
    current_ip: str | None,
    brand: str | None = None,
    model: str | None = None,
    pjlink_name: str | None = None,
    status: str = "unknown",
    classroom_id: int | None = None,
) -> int:
    """
    Registra un nuevo proyector en la base de datos.

    Returns:
        ID del proyector creado.
    """
    with get_db() as conn:
        cursor = conn.execute(
            """
            INSERT INTO projectors
                (classroom_id, mac_address, current_ip, brand, model, pjlink_name, last_seen, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (classroom_id, mac_address, current_ip, brand, model, pjlink_name,
             datetime.now(), status),
        )
        logger.info("Proyector registrado: MAC=%s IP=%s", mac_address, current_ip)
        return cursor.lastrowid


def update_projector_ip(projector_id: int, new_ip: str) -> None:
    """
    Actualiza la IP actual y la marca de tiempo de último avistamiento.
    Se llama cuando el escáner detecta que un proyector cambió de IP.
    """
    with get_db() as conn:
        conn.execute(
            "UPDATE projectors SET current_ip = ?, last_seen = ? WHERE id = ?",
            (new_ip, datetime.now(), projector_id),
        )
    logger.info("IP actualizada para proyector %d: %s", projector_id, new_ip)


def update_projector_status(projector_id: int, status: str) -> None:
    """Actualiza el estado de energía de un proyector ('on', 'off', etc.)."""
    with get_db() as conn:
        conn.execute(
            "UPDATE projectors SET status = ?, last_seen = ? WHERE id = ?",
            (status, datetime.now(), projector_id),
        )


def update_projector_seen(
    projector_id: int,
    ip: str,
    status: str,
    pjlink_name: str | None = None,
    brand: str | None = None,
    model: str | None = None,
) -> None:
    """
    Actualiza todos los campos que puede cambiar entre escaneos:
    IP, estado, nombre PJLink, fabricante, modelo y last_seen.
    """
    with get_db() as conn:
        conn.execute(
            """
            UPDATE projectors
            SET current_ip  = ?,
                status      = ?,
                pjlink_name = COALESCE(?, pjlink_name),
                brand       = COALESCE(?, brand),
                model       = COALESCE(?, model),
                last_seen   = ?
            WHERE id = ?
            """,
            (ip, status, pjlink_name, brand, model, datetime.now(), projector_id),
        )


def assign_projector_to_classroom(projector_id: int, classroom_id: int | None) -> None:
    """
    Asigna o desasigna un proyector a un aula.

    Args:
        projector_id: ID del proyector.
        classroom_id: ID del aula, o None para desasignar.
    """
    with get_db() as conn:
        conn.execute(
            "UPDATE projectors SET classroom_id = ? WHERE id = ?",
            (classroom_id, projector_id),
        )
    logger.info(
        "Proyector %d asignado a aula %s",
        projector_id, classroom_id if classroom_id else "(ninguna)",
    )


def update_projector_mac(projector_id: int, mac_address: str) -> None:
    """Actualiza la MAC address de un proyector (para rotación de hardware)."""
    with get_db() as conn:
        conn.execute(
            "UPDATE projectors SET mac_address = ? WHERE id = ?",
            (mac_address, projector_id),
        )
    logger.info("MAC actualizada para proyector %d: %s", projector_id, mac_address)


# --- Scan log ---

def log_scan_event(
    ip: str,
    event: str,
    mac_address: str | None = None,
) -> None:
    """
    Registra un evento del escáner en el historial.

    Args:
        ip: IP involucrada en el evento.
        event: Tipo de evento: 'discovered', 'ip_changed', 'offline', 'new_mac'.
        mac_address: MAC asociada al evento (opcional).
    """
    with get_db() as conn:
        conn.execute(
            "INSERT INTO scan_log (ip, mac_address, event) VALUES (?, ?, ?)",
            (ip, mac_address, event),
        )
    logger.debug("Evento registrado: %s | IP=%s MAC=%s", event, ip, mac_address)


def get_scan_log(limit: int = 100) -> list[sqlite3.Row]:
    """
    Retorna los últimos eventos del escáner.

    Args:
        limit: Máximo de entradas a retornar (por defecto 100).
    """
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM scan_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()


# --- Función de reconciliación post-escaneo ---

def reconcile_scan_results(scan_results: list) -> dict:
    """
    Procesa los resultados de un escaneo y actualiza la base de datos:
    - Proyector nuevo con MAC conocida → actualiza IP si cambió
    - Proyector nuevo con MAC desconocida → lo registra como no asignado
    - Registra eventos en scan_log

    Args:
        scan_results: Lista de DiscoveredProjector del scanner.

    Returns:
        dict con contadores: updated, new, unchanged.
    """
    counters = {"updated": 0, "new": 0, "unchanged": 0}

    for discovered in scan_results:
        existing = None

        # Buscar por MAC si la tenemos
        if discovered.mac_address:
            existing = get_projector_by_mac(discovered.mac_address)

        if existing:
            # Proyector ya conocido
            if existing["current_ip"] != discovered.ip:
                # IP cambió → actualizar y registrar evento
                old_ip = existing["current_ip"]
                update_projector_seen(
                    projector_id=existing["id"],
                    ip=discovered.ip,
                    status=discovered.power_status,
                    pjlink_name=discovered.pjlink_name,
                    brand=discovered.manufacturer,
                    model=discovered.model,
                )
                log_scan_event(
                    ip=discovered.ip,
                    event="ip_changed",
                    mac_address=discovered.mac_address,
                )
                logger.info(
                    "Proyector %s: IP cambió %s → %s",
                    discovered.mac_address, old_ip, discovered.ip,
                )
                counters["updated"] += 1
            else:
                # Sin cambios, solo actualizar estado y last_seen
                update_projector_seen(
                    projector_id=existing["id"],
                    ip=discovered.ip,
                    status=discovered.power_status,
                    pjlink_name=discovered.pjlink_name,
                    brand=discovered.manufacturer,
                    model=discovered.model,
                )
                counters["unchanged"] += 1
        else:
            # Proyector nuevo
            create_projector(
                mac_address=discovered.mac_address,
                current_ip=discovered.ip,
                brand=discovered.manufacturer,
                model=discovered.model,
                pjlink_name=discovered.pjlink_name,
                status=discovered.power_status,
            )
            log_scan_event(
                ip=discovered.ip,
                event="discovered",
                mac_address=discovered.mac_address,
            )
            counters["new"] += 1

    logger.info(
        "Reconciliación completada: %d nuevos, %d actualizados, %d sin cambios",
        counters["new"], counters["updated"], counters["unchanged"],
    )
    return counters
