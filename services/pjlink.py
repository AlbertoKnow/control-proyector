"""
Módulo de protocolo PJLink para control de proyectores.
Implementa comunicación PJLink Clase 1 sobre TCP sin autenticación.
"""

import socket
import logging
from config import PJLINK_PORT, DEFAULT_TIMEOUT

logger = logging.getLogger(__name__)

# --- Constantes de protocolo ---
PJLINK_GREETING_PREFIX = "PJLINK"
CRLF = "\r"

# Mapeo de estado de energía
POWER_STATUS: dict[str, str] = {
    "0": "off",
    "1": "on",
    "2": "cooling",
    "3": "warming",
}

# Mapeo de códigos de error PJLink
ERROR_CODES: dict[str, str] = {
    "ERR1": "Comando no definido",
    "ERR2": "Parámetro fuera de rango",
    "ERR3": "Proyector ocupado o en transición",
    "ERR4": "Fallo en el proyector",
    "ERRA": "Error de autenticación",
}


# --- Excepciones personalizadas ---

class PJLinkError(Exception):
    """Error base del módulo PJLink."""


class PJLinkConnectionError(PJLinkError):
    """No se pudo establecer conexión TCP con el proyector."""


class PJLinkTimeoutError(PJLinkError):
    """La conexión o respuesta excedió el tiempo límite."""


class PJLinkAuthError(PJLinkError):
    """El proyector requiere autenticación (PJLINK 1)."""


class PJLinkProtocolError(PJLinkError):
    """Respuesta inesperada o inválida del proyector."""


class PJLinkCommandError(PJLinkError):
    """El proyector devolvió un código de error ante un comando."""

    def __init__(self, code: str) -> None:
        self.code = code
        mensaje = ERROR_CODES.get(code, f"Error desconocido: {code}")
        super().__init__(f"{code}: {mensaje}")


# --- Clase de conexión ---

class PJLinkConnection:
    """
    Gestiona una conexión TCP a un proyector vía PJLink.

    Uso como context manager:
        with PJLinkConnection("10.225.71.52") as pj:
            estado = pj.get_power_status()
    """

    def __init__(self, ip: str, port: int = PJLINK_PORT, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket | None = None

    def __enter__(self) -> "PJLinkConnection":
        self._connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._close()

    def _connect(self) -> None:
        """Abre la conexión TCP y valida el saludo PJLink."""
        try:
            self._sock = socket.create_connection(
                (self.ip, self.port), timeout=self.timeout
            )
        except TimeoutError as e:
            raise PJLinkTimeoutError(f"Tiempo agotado al conectar a {self.ip}:{self.port}") from e
        except ConnectionRefusedError as e:
            raise PJLinkConnectionError(f"Conexión rechazada por {self.ip}:{self.port}") from e
        except OSError as e:
            raise PJLinkConnectionError(f"Error de red al conectar a {self.ip}: {e}") from e

        # Leer y validar saludo: "PJLINK 0\r"
        greeting = self._read_line()
        logger.debug("Saludo recibido de %s: %r", self.ip, greeting)

        if not greeting.startswith(PJLINK_GREETING_PREFIX):
            raise PJLinkProtocolError(f"Saludo inesperado: {greeting!r}")

        parts = greeting.split()
        if len(parts) < 2:
            raise PJLinkProtocolError(f"Saludo malformado: {greeting!r}")

        auth_mode = parts[1]
        if auth_mode == "1":
            raise PJLinkAuthError(f"{self.ip} requiere autenticación (PJLINK 1)")
        if auth_mode != "0":
            raise PJLinkProtocolError(f"Modo de autenticación desconocido: {auth_mode!r}")

    def _close(self) -> None:
        """Cierra el socket si está abierto."""
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def _read_line(self) -> str:
        """
        Lee bytes del socket hasta encontrar \\r y devuelve la línea decodificada.
        """
        if not self._sock:
            raise PJLinkConnectionError("Socket no inicializado")

        data = b""
        try:
            while True:
                chunk = self._sock.recv(1)
                if not chunk:
                    break
                data += chunk
                if chunk == b"\r":
                    break
        except TimeoutError as e:
            raise PJLinkTimeoutError(f"Tiempo agotado leyendo respuesta de {self.ip}") from e
        except OSError as e:
            raise PJLinkConnectionError(f"Error leyendo datos de {self.ip}: {e}") from e

        return data.decode("ascii", errors="replace").strip()

    def send_command(self, command: str) -> str:
        """
        Envía un comando PJLink y retorna la respuesta.

        Args:
            command: Comando completo sin \\r, ej: '%1POWR ?'

        Returns:
            Respuesta del proyector, ej: '%1POWR=1'

        Raises:
            PJLinkCommandError: Si la respuesta contiene un código ERRx.
        """
        if not self._sock:
            raise PJLinkConnectionError("Socket no inicializado")

        payload = (command + CRLF).encode("ascii")
        logger.debug("Enviando a %s: %r", self.ip, payload)

        try:
            self._sock.sendall(payload)
        except OSError as e:
            raise PJLinkConnectionError(f"Error enviando comando a {self.ip}: {e}") from e

        response = self._read_line()
        logger.debug("Respuesta de %s: %r", self.ip, response)

        # Verificar códigos de error en la respuesta
        for code in ERROR_CODES:
            if response.endswith(code):
                raise PJLinkCommandError(code)

        return response

    # --- Comandos de alto nivel ---

    def get_power_status(self) -> str:
        """
        Consulta el estado de energía del proyector.

        Returns:
            'on', 'off', 'cooling', 'warming' o 'unknown'
        """
        response = self.send_command("%1POWR ?")
        # Formato esperado: '%1POWR=X'
        value = _parse_response(response, "POWR")
        return POWER_STATUS.get(value, "unknown")

    def power_on(self) -> bool:
        """
        Enciende el proyector.

        Returns:
            True si el comando fue aceptado.
        """
        response = self.send_command("%1POWR 1")
        return _parse_response(response, "POWR") == "OK"

    def power_off(self) -> bool:
        """
        Apaga el proyector.

        Returns:
            True si el comando fue aceptado.
        """
        response = self.send_command("%1POWR 0")
        return _parse_response(response, "POWR") == "OK"

    def get_name(self) -> str:
        """Retorna el nombre PJLink del proyector."""
        response = self.send_command("%1NAME ?")
        return _parse_response(response, "NAME")

    def get_manufacturer(self) -> str:
        """Retorna el fabricante del proyector."""
        response = self.send_command("%1INF1 ?")
        return _parse_response(response, "INF1")

    def get_model(self) -> str:
        """Retorna el modelo del proyector."""
        response = self.send_command("%1INF2 ?")
        return _parse_response(response, "INF2")

    def get_info(self) -> dict:
        """
        Consulta nombre, fabricante, modelo y estado de energía en una sola conexión.

        Returns:
            dict con claves: name, manufacturer, model, power_status
        """
        return {
            "name": self.get_name(),
            "manufacturer": self.get_manufacturer(),
            "model": self.get_model(),
            "power_status": self.get_power_status(),
        }


# --- Funciones de utilidad ---

def _parse_response(response: str, command: str) -> str:
    """
    Extrae el valor de una respuesta PJLink.

    Ejemplo: '%1POWR=1' con command='POWR' → '1'

    Raises:
        PJLinkProtocolError: Si el formato no coincide.
    """
    expected_prefix = f"%1{command}="
    if not response.startswith(expected_prefix):
        raise PJLinkProtocolError(
            f"Respuesta inesperada para {command}: {response!r}"
        )
    return response[len(expected_prefix):]


def get_projector_status(ip: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Función de conveniencia: conecta, consulta estado y cierra.

    Args:
        ip: Dirección IP del proyector.
        timeout: Tiempo límite en segundos.

    Returns:
        dict con 'status' y opcionalmente 'error' y 'message'.
    """
    try:
        with PJLinkConnection(ip, timeout=timeout) as pj:
            status = pj.get_power_status()
        return {"status": status}
    except PJLinkTimeoutError:
        logger.warning("Timeout al consultar estado de %s", ip)
        return {"status": "unreachable", "message": "Proyector no responde"}
    except PJLinkConnectionError:
        logger.warning("Conexión rechazada por %s", ip)
        return {"status": "offline", "message": "Puerto cerrado"}
    except PJLinkError as e:
        logger.error("Error PJLink en %s: %s", ip, e)
        return {"status": "unknown", "message": str(e)}


def send_power_command(ip: str, turn_on: bool, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    Función de conveniencia: envía comando de encendido o apagado.

    Args:
        ip: Dirección IP del proyector.
        turn_on: True para encender, False para apagar.
        timeout: Tiempo límite en segundos.

    Returns:
        dict con 'success' (bool) y opcionalmente 'error'.
    """
    accion = "encender" if turn_on else "apagar"
    try:
        with PJLinkConnection(ip, timeout=timeout) as pj:
            ok = pj.power_on() if turn_on else pj.power_off()
        if ok:
            logger.info("Comando %s ejecutado en %s", accion, ip)
        return {"success": ok}
    except PJLinkTimeoutError:
        logger.warning("Timeout al %s proyector %s", accion, ip)
        return {"success": False, "error": "Proyector no responde"}
    except PJLinkConnectionError:
        logger.warning("Sin conexión al %s proyector %s", accion, ip)
        return {"success": False, "error": "No se pudo conectar"}
    except PJLinkCommandError as e:
        logger.warning("Error de comando al %s proyector %s: %s", accion, ip, e)
        return {"success": False, "error": str(e)}
    except PJLinkError as e:
        logger.error("Error PJLink al %s proyector %s: %s", accion, ip, e)
        return {"success": False, "error": str(e)}
