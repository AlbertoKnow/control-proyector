"""
Módulo de escaneo de red para descubrir proyectores PJLink.
Detecta proyectores activos en las subredes configuradas e identifica
su MAC address mediante la tabla ARP del sistema operativo.
"""

import re
import socket
import subprocess
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime

from config import (
    PJLINK_PORT,
    SCAN_TIMEOUT,
    SCAN_HOST_START,
    SCAN_HOST_END,
    SUBNETS,
)
from services.pjlink import PJLinkConnection, PJLinkError

logger = logging.getLogger(__name__)

# Máximo de hilos concurrentes para el escaneo
MAX_WORKERS: int = 50

# Regex para parsear la salida de arp -a en Windows
# Ejemplo de línea: "  10.225.71.52         aa-bb-cc-dd-ee-ff     dinámico"
_ARP_PATTERN = re.compile(
    r"(\d{1,3}(?:\.\d{1,3}){3})\s+([\da-fA-F]{2}[:-][\da-fA-F]{2}[:-][\da-fA-F]{2}"
    r"[:-][\da-fA-F]{2}[:-][\da-fA-F]{2}[:-][\da-fA-F]{2})"
)


@dataclass
class DiscoveredProjector:
    """Resultado de un proyector encontrado durante el escaneo."""
    ip: str
    mac_address: str | None
    pjlink_name: str | None
    manufacturer: str | None
    model: str | None
    power_status: str
    scanned_at: datetime = field(default_factory=datetime.now)


def is_pjlink_port_open(ip: str, timeout: int = SCAN_TIMEOUT) -> bool:
    """
    Verifica si el puerto PJLink está abierto en una IP dada.

    Args:
        ip: Dirección IP a probar.
        timeout: Segundos máximos de espera.

    Returns:
        True si el puerto 4352 responde.
    """
    try:
        with socket.create_connection((ip, PJLINK_PORT), timeout=timeout):
            return True
    except OSError:
        return False


def get_mac_from_arp(ip: str) -> str | None:
    """
    Obtiene la MAC address de una IP desde la tabla ARP del sistema.
    Funciona en Windows usando 'arp -a'.

    La MAC queda cacheada en ARP luego de una conexión TCP previa.

    Args:
        ip: Dirección IP del proyector.

    Returns:
        MAC address en formato 'AA:BB:CC:DD:EE:FF' o None si no se encuentra.
    """
    try:
        result = subprocess.run(
            ["arp", "-a", ip],
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = result.stdout + result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Error ejecutando arp -a para %s: %s", ip, e)
        return None

    for line in output.splitlines():
        match = _ARP_PATTERN.search(line)
        if match and match.group(1) == ip:
            # Normalizar separadores a ':' y mayúsculas
            mac_raw = match.group(2)
            mac = mac_raw.upper().replace("-", ":")
            logger.debug("MAC encontrada para %s: %s", ip, mac)
            return mac

    logger.debug("MAC no encontrada en ARP para %s", ip)
    return None


def probe_projector(ip: str) -> DiscoveredProjector | None:
    """
    Intenta conectarse a un proyector vía PJLink y obtener su información.
    Tras la conexión TCP, consulta la MAC desde la tabla ARP.

    Args:
        ip: Dirección IP a probar.

    Returns:
        DiscoveredProjector con la información obtenida, o None si no es un proyector PJLink.
    """
    logger.debug("Sondeando %s...", ip)

    # Verificación rápida de puerto antes de intentar PJLink completo
    if not is_pjlink_port_open(ip):
        return None

    # Intentar conexión PJLink y obtener datos
    pjlink_name = None
    manufacturer = None
    model = None
    power_status = "unknown"

    try:
        with PJLinkConnection(ip) as pj:
            power_status = pj.get_power_status()
            # Obtener info adicional; cada llamada puede fallar individualmente
            try:
                pjlink_name = pj.get_name()
            except PJLinkError:
                pass
            try:
                manufacturer = pj.get_manufacturer()
            except PJLinkError:
                pass
            try:
                model = pj.get_model()
            except PJLinkError:
                pass
    except PJLinkError as e:
        logger.warning("Error PJLink al sondear %s: %s", ip, e)
        # El puerto estaba abierto pero PJLink falló — no es un proyector válido
        return None

    # Consultar ARP después de la conexión TCP (la MAC queda cacheada)
    mac = get_mac_from_arp(ip)

    logger.info(
        "Proyector encontrado en %s | MAC: %s | %s %s | Estado: %s",
        ip, mac, manufacturer, model, power_status,
    )

    return DiscoveredProjector(
        ip=ip,
        mac_address=mac,
        pjlink_name=pjlink_name,
        manufacturer=manufacturer,
        model=model,
        power_status=power_status,
    )


def scan_subnet(subnet: str) -> list[DiscoveredProjector]:
    """
    Escanea todos los hosts de una subred buscando proyectores PJLink.
    Usa hilos concurrentes para reducir el tiempo de escaneo.

    Args:
        subnet: Prefijo de subred, ej: '10.225.71'

    Returns:
        Lista de DiscoveredProjector encontrados.
    """
    hosts = [
        f"{subnet}.{i}"
        for i in range(SCAN_HOST_START, SCAN_HOST_END + 1)
    ]

    logger.info(
        "Iniciando escaneo de %s.%d-%d (%d hosts)",
        subnet, SCAN_HOST_START, SCAN_HOST_END, len(hosts),
    )

    found: list[DiscoveredProjector] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(probe_projector, ip): ip for ip in hosts}

        for future in as_completed(futures):
            ip = futures[future]
            try:
                result = future.result()
                if result is not None:
                    found.append(result)
            except Exception as e:
                logger.error("Error inesperado sondeando %s: %s", ip, e)

    logger.info("Escaneo de %s completado: %d proyector(es) encontrado(s)", subnet, len(found))
    return found


def scan_all_subnets(subnets: list[str] | None = None) -> list[DiscoveredProjector]:
    """
    Escanea todas las subredes configuradas.

    Args:
        subnets: Lista de subredes a escanear. Si es None, usa SUBNETS de config.

    Returns:
        Lista combinada de todos los proyectores encontrados.
    """
    targets = subnets if subnets is not None else SUBNETS
    all_found: list[DiscoveredProjector] = []

    for subnet in targets:
        results = scan_subnet(subnet)
        all_found.extend(results)

    logger.info(
        "Escaneo total completado: %d proyector(es) en %d subred(es)",
        len(all_found), len(targets),
    )
    return all_found
