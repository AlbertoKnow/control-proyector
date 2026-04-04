"""
Tests unitarios del módulo scanner.
Usa mocks para simular conexiones de red y salida de arp.
"""

import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime

from services.scanner import (
    get_mac_from_arp,
    is_pjlink_port_open,
    probe_projector,
    DiscoveredProjector,
)


class TestGetMacFromArp(unittest.TestCase):
    """Tests del parseo de la tabla ARP."""

    # Salida real de 'arp -a 10.225.71.52' en Windows
    ARP_OUTPUT_WINDOWS = (
        "\nInterfaz: 10.225.30.5 --- 0x5\n"
        "  Dirección de Internet      Dirección física      Tipo\n"
        "  10.225.71.52          aa-bb-cc-dd-ee-ff     dinámico\n"
    )

    ARP_OUTPUT_NO_MATCH = (
        "\nInterfaz: 10.225.30.5 --- 0x5\n"
        "  Dirección de Internet      Dirección física      Tipo\n"
        "  10.225.71.99          11-22-33-44-55-66     dinámico\n"
    )

    @patch("services.scanner.subprocess.run")
    def test_mac_encontrada_y_normalizada(self, mock_run):
        """Retorna MAC en formato AA:BB:CC:DD:EE:FF."""
        mock_run.return_value = MagicMock(
            stdout=self.ARP_OUTPUT_WINDOWS, stderr=""
        )
        mac = get_mac_from_arp("10.225.71.52")
        self.assertEqual(mac, "AA:BB:CC:DD:EE:FF")

    @patch("services.scanner.subprocess.run")
    def test_mac_no_encontrada_retorna_none(self, mock_run):
        """Retorna None si la IP no está en la tabla ARP."""
        mock_run.return_value = MagicMock(
            stdout=self.ARP_OUTPUT_NO_MATCH, stderr=""
        )
        mac = get_mac_from_arp("10.225.71.52")
        self.assertIsNone(mac)

    @patch("services.scanner.subprocess.run")
    def test_salida_vacia_retorna_none(self, mock_run):
        """Retorna None si arp no devuelve nada."""
        mock_run.return_value = MagicMock(stdout="", stderr="")
        mac = get_mac_from_arp("10.225.71.52")
        self.assertIsNone(mac)

    @patch("services.scanner.subprocess.run")
    def test_timeout_retorna_none(self, mock_run):
        """Retorna None si subprocess lanza TimeoutExpired."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="arp", timeout=5)
        mac = get_mac_from_arp("10.225.71.52")
        self.assertIsNone(mac)

    @patch("services.scanner.subprocess.run")
    def test_arp_no_disponible_retorna_none(self, mock_run):
        """Retorna None si el comando arp no existe."""
        mock_run.side_effect = FileNotFoundError()
        mac = get_mac_from_arp("10.225.71.52")
        self.assertIsNone(mac)

    @patch("services.scanner.subprocess.run")
    def test_mac_con_dos_puntos_tambien_parsea(self, mock_run):
        """Acepta MACs con ':' como separador además de '-'."""
        output = "  10.0.0.1    AA:BB:CC:DD:EE:FF    estático\n"
        mock_run.return_value = MagicMock(stdout=output, stderr="")
        mac = get_mac_from_arp("10.0.0.1")
        self.assertEqual(mac, "AA:BB:CC:DD:EE:FF")


class TestIsPjlinkPortOpen(unittest.TestCase):
    """Tests de la verificación rápida de puerto."""

    @patch("services.scanner.socket.create_connection")
    def test_puerto_abierto_retorna_true(self, mock_conn):
        mock_conn.return_value = MagicMock()
        self.assertTrue(is_pjlink_port_open("10.0.0.1"))

    @patch("services.scanner.socket.create_connection")
    def test_conexion_rechazada_retorna_false(self, mock_conn):
        mock_conn.side_effect = ConnectionRefusedError()
        self.assertFalse(is_pjlink_port_open("10.0.0.1"))

    @patch("services.scanner.socket.create_connection")
    def test_timeout_retorna_false(self, mock_conn):
        mock_conn.side_effect = TimeoutError()
        self.assertFalse(is_pjlink_port_open("10.0.0.1"))

    @patch("services.scanner.socket.create_connection")
    def test_error_red_retorna_false(self, mock_conn):
        mock_conn.side_effect = OSError("Network unreachable")
        self.assertFalse(is_pjlink_port_open("10.0.0.1"))


class TestProbeProjector(unittest.TestCase):
    """Tests del sondeo completo de un proyector."""

    @patch("services.scanner.get_mac_from_arp")
    @patch("services.scanner.PJLinkConnection")
    @patch("services.scanner.is_pjlink_port_open")
    def test_proyector_encontrado_completo(self, mock_open, MockConn, mock_arp):
        """Retorna DiscoveredProjector con todos los campos cuando todo funciona."""
        mock_open.return_value = True
        mock_arp.return_value = "AA:BB:CC:DD:EE:FF"

        instance = MockConn.return_value.__enter__.return_value
        instance.get_power_status.return_value = "on"
        instance.get_name.return_value = "PG707X"
        instance.get_manufacturer.return_value = "ViewSonic"
        instance.get_model.return_value = "Data Projector"

        result = probe_projector("10.225.71.52")

        self.assertIsNotNone(result)
        self.assertIsInstance(result, DiscoveredProjector)
        self.assertEqual(result.ip, "10.225.71.52")
        self.assertEqual(result.mac_address, "AA:BB:CC:DD:EE:FF")
        self.assertEqual(result.power_status, "on")
        self.assertEqual(result.pjlink_name, "PG707X")
        self.assertEqual(result.manufacturer, "ViewSonic")
        self.assertEqual(result.model, "Data Projector")

    @patch("services.scanner.is_pjlink_port_open")
    def test_puerto_cerrado_retorna_none(self, mock_open):
        """Si el puerto no responde, retorna None sin intentar PJLink."""
        mock_open.return_value = False
        result = probe_projector("10.225.71.99")
        self.assertIsNone(result)

    @patch("services.scanner.get_mac_from_arp")
    @patch("services.scanner.PJLinkConnection")
    @patch("services.scanner.is_pjlink_port_open")
    def test_proyector_sin_mac(self, mock_open, MockConn, mock_arp):
        """Retorna DiscoveredProjector con mac_address=None si ARP no responde."""
        mock_open.return_value = True
        mock_arp.return_value = None

        instance = MockConn.return_value.__enter__.return_value
        instance.get_power_status.return_value = "off"
        instance.get_name.return_value = "NEC-001"
        instance.get_manufacturer.return_value = "NEC"
        instance.get_model.return_value = "ME403"

        result = probe_projector("10.225.71.10")

        self.assertIsNotNone(result)
        self.assertIsNone(result.mac_address)
        self.assertEqual(result.power_status, "off")

    @patch("services.scanner.PJLinkConnection")
    @patch("services.scanner.is_pjlink_port_open")
    def test_fallo_pjlink_retorna_none(self, mock_open, MockConn):
        """Si PJLink falla tras puerto abierto, retorna None."""
        from services.pjlink import PJLinkConnectionError
        mock_open.return_value = True
        MockConn.return_value.__enter__.side_effect = PJLinkConnectionError("fail")

        result = probe_projector("10.225.71.1")
        self.assertIsNone(result)

    @patch("services.scanner.get_mac_from_arp")
    @patch("services.scanner.PJLinkConnection")
    @patch("services.scanner.is_pjlink_port_open")
    def test_info_parcial_cuando_comandos_fallan(self, mock_open, MockConn, mock_arp):
        """
        Si get_name/manufacturer/model lanzan PJLinkError, el sondeo
        igual retorna el proyector con los campos disponibles.
        """
        from services.pjlink import PJLinkCommandError
        mock_open.return_value = True
        mock_arp.return_value = "11:22:33:44:55:66"

        instance = MockConn.return_value.__enter__.return_value
        instance.get_power_status.return_value = "on"
        instance.get_name.side_effect = PJLinkCommandError("ERR1")
        instance.get_manufacturer.side_effect = PJLinkCommandError("ERR1")
        instance.get_model.side_effect = PJLinkCommandError("ERR1")

        result = probe_projector("10.225.71.20")

        self.assertIsNotNone(result)
        self.assertEqual(result.power_status, "on")
        self.assertIsNone(result.pjlink_name)
        self.assertIsNone(result.manufacturer)
        self.assertIsNone(result.model)


class TestDiscoveredProjectorDataclass(unittest.TestCase):
    """Tests básicos del dataclass DiscoveredProjector."""

    def test_campos_requeridos(self):
        p = DiscoveredProjector(
            ip="10.0.0.1",
            mac_address="AA:BB:CC:DD:EE:FF",
            pjlink_name="TEST",
            manufacturer="NEC",
            model="ME403",
            power_status="on",
        )
        self.assertEqual(p.ip, "10.0.0.1")
        self.assertIsInstance(p.scanned_at, datetime)

    def test_campos_opcionales_none(self):
        p = DiscoveredProjector(
            ip="10.0.0.2",
            mac_address=None,
            pjlink_name=None,
            manufacturer=None,
            model=None,
            power_status="unknown",
        )
        self.assertIsNone(p.mac_address)
        self.assertEqual(p.power_status, "unknown")


if __name__ == "__main__":
    unittest.main()
