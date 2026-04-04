"""
Tests unitarios del módulo PJLink.
Usa mocks para simular conexiones TCP sin necesidad de proyectores reales.
"""

import unittest
from unittest.mock import MagicMock, patch, call

from services.pjlink import (
    PJLinkConnection,
    PJLinkAuthError,
    PJLinkCommandError,
    PJLinkConnectionError,
    PJLinkProtocolError,
    PJLinkTimeoutError,
    _parse_response,
    get_projector_status,
    send_power_command,
)


class TestParseResponse(unittest.TestCase):
    """Tests para la función auxiliar _parse_response."""

    def test_parsea_estado_correcto(self):
        self.assertEqual(_parse_response("%1POWR=1", "POWR"), "1")

    def test_parsea_ok(self):
        self.assertEqual(_parse_response("%1POWR=OK", "POWR"), "OK")

    def test_parsea_nombre(self):
        self.assertEqual(_parse_response("%1NAME=PG707X", "NAME"), "PG707X")

    def test_parsea_fabricante(self):
        self.assertEqual(_parse_response("%1INF1=ViewSonic", "INF1"), "ViewSonic")

    def test_prefijo_incorrecto_lanza_error(self):
        with self.assertRaises(PJLinkProtocolError):
            _parse_response("%1NAME=algo", "POWR")

    def test_respuesta_vacia_lanza_error(self):
        with self.assertRaises(PJLinkProtocolError):
            _parse_response("", "POWR")


class TestPJLinkConnectionGreeting(unittest.TestCase):
    """Tests del handshake inicial PJLink."""

    def _make_conn(self, greeting_bytes: bytes) -> PJLinkConnection:
        """Crea una PJLinkConnection con socket mockeado."""
        conn = PJLinkConnection("10.0.0.1")
        mock_sock = MagicMock()
        # Simular lectura byte a byte
        mock_sock.recv.side_effect = [bytes([b]) for b in greeting_bytes]
        conn._sock = mock_sock
        return conn

    @patch("services.pjlink.socket.create_connection")
    def test_saludo_valido_no_lanza(self, mock_create):
        """PJLINK 0\\r es aceptado sin excepción."""
        mock_sock = MagicMock()
        greeting = b"PJLINK 0\r"
        mock_sock.recv.side_effect = [bytes([b]) for b in greeting]
        mock_create.return_value = mock_sock

        conn = PJLinkConnection("10.0.0.1")
        conn._connect()   # no debe lanzar

    @patch("services.pjlink.socket.create_connection")
    def test_saludo_auth_lanza_error(self, mock_create):
        """PJLINK 1\\r lanza PJLinkAuthError."""
        mock_sock = MagicMock()
        greeting = b"PJLINK 1\r"
        mock_sock.recv.side_effect = [bytes([b]) for b in greeting]
        mock_create.return_value = mock_sock

        conn = PJLinkConnection("10.0.0.1")
        with self.assertRaises(PJLinkAuthError):
            conn._connect()

    @patch("services.pjlink.socket.create_connection")
    def test_saludo_inesperado_lanza_error(self, mock_create):
        """Un saludo desconocido lanza PJLinkProtocolError."""
        mock_sock = MagicMock()
        greeting = b"HTTP/1.1 200 OK\r"
        mock_sock.recv.side_effect = [bytes([b]) for b in greeting]
        mock_create.return_value = mock_sock

        conn = PJLinkConnection("10.0.0.1")
        with self.assertRaises(PJLinkProtocolError):
            conn._connect()

    @patch("services.pjlink.socket.create_connection")
    def test_timeout_al_conectar_lanza_error(self, mock_create):
        """TimeoutError al conectar → PJLinkTimeoutError."""
        mock_create.side_effect = TimeoutError()
        conn = PJLinkConnection("10.0.0.1")
        with self.assertRaises(PJLinkTimeoutError):
            conn._connect()

    @patch("services.pjlink.socket.create_connection")
    def test_conexion_rechazada_lanza_error(self, mock_create):
        """ConnectionRefusedError → PJLinkConnectionError."""
        mock_create.side_effect = ConnectionRefusedError()
        conn = PJLinkConnection("10.0.0.1")
        with self.assertRaises(PJLinkConnectionError):
            conn._connect()


class TestPJLinkCommands(unittest.TestCase):
    """Tests de los comandos de alto nivel sobre socket mockeado."""

    def _make_connected_conn(self, responses: list[bytes]) -> PJLinkConnection:
        """
        Retorna una PJLinkConnection ya 'conectada' con respuestas predefinidas.
        responses: lista de cadenas de bytes que recv devolverá byte a byte.
        """
        conn = PJLinkConnection("10.0.0.1")
        mock_sock = MagicMock()

        # Aplanar todas las respuestas en secuencia byte a byte
        all_bytes = []
        for response in responses:
            all_bytes.extend([bytes([b]) for b in response])

        mock_sock.recv.side_effect = all_bytes
        conn._sock = mock_sock
        return conn

    def test_get_power_status_on(self):
        conn = self._make_connected_conn([b"%1POWR=1\r"])
        self.assertEqual(conn.get_power_status(), "on")

    def test_get_power_status_off(self):
        conn = self._make_connected_conn([b"%1POWR=0\r"])
        self.assertEqual(conn.get_power_status(), "off")

    def test_get_power_status_warming(self):
        conn = self._make_connected_conn([b"%1POWR=3\r"])
        self.assertEqual(conn.get_power_status(), "warming")

    def test_get_power_status_cooling(self):
        conn = self._make_connected_conn([b"%1POWR=2\r"])
        self.assertEqual(conn.get_power_status(), "cooling")

    def test_get_power_status_desconocido(self):
        conn = self._make_connected_conn([b"%1POWR=9\r"])
        self.assertEqual(conn.get_power_status(), "unknown")

    def test_power_on_retorna_true(self):
        conn = self._make_connected_conn([b"%1POWR=OK\r"])
        self.assertTrue(conn.power_on())

    def test_power_off_retorna_true(self):
        conn = self._make_connected_conn([b"%1POWR=OK\r"])
        self.assertTrue(conn.power_off())

    def test_get_name(self):
        conn = self._make_connected_conn([b"%1NAME=PG707X\r"])
        self.assertEqual(conn.get_name(), "PG707X")

    def test_get_manufacturer(self):
        conn = self._make_connected_conn([b"%1INF1=ViewSonic\r"])
        self.assertEqual(conn.get_manufacturer(), "ViewSonic")

    def test_get_model(self):
        conn = self._make_connected_conn([b"%1INF2=Data Projector\r"])
        self.assertEqual(conn.get_model(), "Data Projector")

    def test_get_info_completo(self):
        conn = self._make_connected_conn([
            b"%1NAME=PG707X\r",
            b"%1INF1=ViewSonic\r",
            b"%1INF2=Data Projector\r",
            b"%1POWR=1\r",
        ])
        info = conn.get_info()
        self.assertEqual(info["name"], "PG707X")
        self.assertEqual(info["manufacturer"], "ViewSonic")
        self.assertEqual(info["model"], "Data Projector")
        self.assertEqual(info["power_status"], "on")


class TestPJLinkErrorCodes(unittest.TestCase):
    """Tests de manejo de códigos de error ERRx."""

    def _conn_with_response(self, response: bytes) -> PJLinkConnection:
        conn = PJLinkConnection("10.0.0.1")
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [bytes([b]) for b in response]
        conn._sock = mock_sock
        return conn

    def test_err1_lanza_command_error(self):
        conn = self._conn_with_response(b"%1POWR=ERR1\r")
        with self.assertRaises(PJLinkCommandError) as ctx:
            conn.get_power_status()
        self.assertEqual(ctx.exception.code, "ERR1")

    def test_err3_lanza_command_error(self):
        conn = self._conn_with_response(b"%1POWR=ERR3\r")
        with self.assertRaises(PJLinkCommandError) as ctx:
            conn.power_on()
        self.assertEqual(ctx.exception.code, "ERR3")

    def test_err4_lanza_command_error(self):
        conn = self._conn_with_response(b"%1POWR=ERR4\r")
        with self.assertRaises(PJLinkCommandError) as ctx:
            conn.power_off()
        self.assertEqual(ctx.exception.code, "ERR4")

    def test_erra_lanza_command_error(self):
        conn = self._conn_with_response(b"%1POWR=ERRA\r")
        with self.assertRaises(PJLinkCommandError) as ctx:
            conn.get_power_status()
        self.assertEqual(ctx.exception.code, "ERRA")


class TestConvenienceFunctions(unittest.TestCase):
    """Tests de get_projector_status y send_power_command."""

    @patch("services.pjlink.PJLinkConnection")
    def test_get_status_exitoso(self, MockConn):
        instance = MockConn.return_value.__enter__.return_value
        instance.get_power_status.return_value = "on"

        result = get_projector_status("10.0.0.1")
        self.assertEqual(result, {"status": "on"})

    @patch("services.pjlink.PJLinkConnection")
    def test_get_status_timeout(self, MockConn):
        MockConn.return_value.__enter__.side_effect = PJLinkTimeoutError("timeout")

        result = get_projector_status("10.0.0.1")
        self.assertEqual(result["status"], "unreachable")
        self.assertIn("message", result)

    @patch("services.pjlink.PJLinkConnection")
    def test_get_status_offline(self, MockConn):
        MockConn.return_value.__enter__.side_effect = PJLinkConnectionError("refused")

        result = get_projector_status("10.0.0.1")
        self.assertEqual(result["status"], "offline")

    @patch("services.pjlink.PJLinkConnection")
    def test_power_command_encender_exitoso(self, MockConn):
        instance = MockConn.return_value.__enter__.return_value
        instance.power_on.return_value = True

        result = send_power_command("10.0.0.1", turn_on=True)
        self.assertTrue(result["success"])
        instance.power_on.assert_called_once()

    @patch("services.pjlink.PJLinkConnection")
    def test_power_command_apagar_exitoso(self, MockConn):
        instance = MockConn.return_value.__enter__.return_value
        instance.power_off.return_value = True

        result = send_power_command("10.0.0.1", turn_on=False)
        self.assertTrue(result["success"])
        instance.power_off.assert_called_once()

    @patch("services.pjlink.PJLinkConnection")
    def test_power_command_fallo_conexion(self, MockConn):
        MockConn.return_value.__enter__.side_effect = PJLinkConnectionError("no route")

        result = send_power_command("10.0.0.1", turn_on=True)
        self.assertFalse(result["success"])
        self.assertIn("error", result)

    @patch("services.pjlink.PJLinkConnection")
    def test_power_command_fallo_err3(self, MockConn):
        instance = MockConn.return_value.__enter__.return_value
        instance.power_on.side_effect = PJLinkCommandError("ERR3")

        result = send_power_command("10.0.0.1", turn_on=True)
        self.assertFalse(result["success"])
        self.assertIn("ERR3", result["error"])


if __name__ == "__main__":
    unittest.main()
