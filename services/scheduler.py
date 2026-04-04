"""
Módulo de escaneo periódico automático de ProyControl.
Ejecuta un escaneo de red en segundo plano cada SCAN_INTERVAL_SECONDS.
"""

import logging
import threading
from datetime import datetime

from config import SCAN_INTERVAL_SECONDS
from models.database import reconcile_scan_results
from services.scanner import scan_all_subnets

logger = logging.getLogger(__name__)


class ProjectorScheduler:
    """
    Scheduler de escaneo periódico usando un hilo daemon de Python.

    Uso:
        scheduler = ProjectorScheduler()
        scheduler.start()          # arranca el hilo
        scheduler.stop()           # detiene limpiamente
        scheduler.run_now()        # fuerza un escaneo inmediato
    """

    def __init__(self, interval: int = SCAN_INTERVAL_SECONDS) -> None:
        self.interval = interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_run: datetime | None = None
        self._last_result: dict | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Control del hilo
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Inicia el hilo de escaneo periódico si no está corriendo."""
        if self._thread and self._thread.is_alive():
            logger.warning("El scheduler ya está corriendo")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="proycontrol-scheduler",
            daemon=True,        # muere junto con el proceso principal
        )
        self._thread.start()
        logger.info(
            "Scheduler iniciado — intervalo: %d segundos", self.interval
        )

    def stop(self) -> None:
        """Detiene el scheduler y espera a que el hilo termine."""
        if not self._thread or not self._thread.is_alive():
            return

        logger.info("Deteniendo scheduler...")
        self._stop_event.set()
        self._thread.join(timeout=10)
        logger.info("Scheduler detenido")

    def is_running(self) -> bool:
        """Retorna True si el hilo de escaneo está activo."""
        return self._thread is not None and self._thread.is_alive()

    # ------------------------------------------------------------------
    # Escaneo bajo demanda
    # ------------------------------------------------------------------

    def run_now(self) -> dict:
        """
        Ejecuta un escaneo inmediato en el hilo actual (bloqueante).
        Útil para el botón de escaneo manual en la API.

        Returns:
            dict con contadores: projectors_found, new, updated, unchanged.
        """
        return self._run_scan()

    # ------------------------------------------------------------------
    # Estado / telemetría
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """
        Retorna el estado actual del scheduler.

        Returns:
            dict con: running, last_run, last_result, interval_seconds.
        """
        with self._lock:
            return {
                "running": self.is_running(),
                "interval_seconds": self.interval,
                "last_run": self._last_run.isoformat() if self._last_run else None,
                "last_result": self._last_result,
            }

    # ------------------------------------------------------------------
    # Bucle interno
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        """
        Bucle principal del hilo daemon.
        Ejecuta un escaneo y espera hasta el próximo intervalo.
        """
        logger.info("Hilo de escaneo arrancado")

        # Primer escaneo al iniciar, sin esperar el intervalo completo
        self._run_scan()

        while not self._stop_event.wait(timeout=self.interval):
            self._run_scan()

        logger.info("Hilo de escaneo finalizado")

    def _run_scan(self) -> dict:
        """
        Ejecuta el escaneo completo y reconcilia resultados con la BD.

        Returns:
            dict con contadores del escaneo.
        """
        logger.info("Iniciando escaneo automático...")
        start = datetime.now()

        try:
            results = scan_all_subnets()
            counters = reconcile_scan_results(results)

            elapsed = (datetime.now() - start).total_seconds()
            counters["projectors_found"] = len(results)
            counters["elapsed_seconds"] = round(elapsed, 1)

            logger.info(
                "Escaneo completado en %.1fs — encontrados: %d, nuevos: %d, "
                "actualizados: %d, sin cambios: %d",
                elapsed,
                len(results),
                counters["new"],
                counters["updated"],
                counters["unchanged"],
            )

            with self._lock:
                self._last_run = datetime.now()
                self._last_result = counters

            return counters

        except Exception as e:
            logger.error("Error durante el escaneo automático: %s", e, exc_info=True)
            error_result = {
                "projectors_found": 0,
                "new": 0,
                "updated": 0,
                "unchanged": 0,
                "error": str(e),
            }
            with self._lock:
                self._last_run = datetime.now()
                self._last_result = error_result
            return error_result


# Instancia global del scheduler — importada por app.py
scheduler = ProjectorScheduler()
