"""
Endpoints REST de la API de ProyControl.
Cubre operaciones de admin (proyectores, escaneo) y docentes (aulas).
"""

import logging
from flask import Blueprint, jsonify, request

from services.scheduler import scheduler
from models.database import (
    get_all_projectors,
    get_projector,
    get_projector_by_mac,
    get_classroom_by_number,
    get_projector_by_classroom,
    get_scan_log,
    assign_projector_to_classroom,
    update_projector_mac,
    update_projector_status,
)
from services.pjlink import get_projector_status, send_power_command
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _projector_row_to_dict(row) -> dict:
    """Convierte una fila de proyector a dict serializable."""
    return dict(row)


def _error(message: str, status_code: int = 400):
    return jsonify({"error": message}), status_code


def _not_found(resource: str = "Recurso"):
    return _error(f"{resource} no encontrado", 404)


# ---------------------------------------------------------------------------
# Proyectores — admin
# ---------------------------------------------------------------------------

@api_bp.get("/projectors")
def list_projectors():
    """Retorna todos los proyectores con datos de aula y campus."""
    rows = get_all_projectors()
    return jsonify([_projector_row_to_dict(r) for r in rows])


@api_bp.get("/projectors/<int:projector_id>")
def get_projector_detail(projector_id: int):
    """Retorna el detalle de un proyector por ID."""
    row = get_projector(projector_id)
    if row is None:
        return _not_found("Proyector")
    return jsonify(_projector_row_to_dict(row))


@api_bp.get("/projectors/<int:projector_id>/status")
def projector_status(projector_id: int):
    """
    Consulta el estado de energía actual del proyector vía PJLink.
    Requiere que el proyector esté en red.
    """
    row = get_projector(projector_id)
    if row is None:
        return _not_found("Proyector")

    ip = row["current_ip"]
    if not ip:
        return _error("El proyector no tiene IP asignada", 422)

    result = get_projector_status(ip)

    # Actualizar estado en BD si la consulta fue exitosa
    if result["status"] not in ("unreachable", "offline", "unknown"):
        update_projector_status(projector_id, result["status"])

    return jsonify({"id": projector_id, "ip": ip, **result})


@api_bp.post("/projectors/<int:projector_id>/power-on")
def power_on_projector(projector_id: int):
    """Enciende el proyector especificado vía PJLink."""
    row = get_projector(projector_id)
    if row is None:
        return _not_found("Proyector")

    ip = row["current_ip"]
    if not ip:
        return _error("El proyector no tiene IP asignada", 422)

    result = send_power_command(ip, turn_on=True)
    if result["success"]:
        update_projector_status(projector_id, "warming")
    return jsonify({"id": projector_id, "ip": ip, **result})


@api_bp.post("/projectors/<int:projector_id>/power-off")
def power_off_projector(projector_id: int):
    """Apaga el proyector especificado vía PJLink."""
    row = get_projector(projector_id)
    if row is None:
        return _not_found("Proyector")

    ip = row["current_ip"]
    if not ip:
        return _error("El proyector no tiene IP asignada", 422)

    result = send_power_command(ip, turn_on=False)
    if result["success"]:
        update_projector_status(projector_id, "cooling")
    return jsonify({"id": projector_id, "ip": ip, **result})


@api_bp.post("/projectors/power-on-all")
def power_on_all():
    """Enciende todos los proyectores con IP asignada en paralelo."""
    return _bulk_power_action(turn_on=True)


@api_bp.post("/projectors/power-off-all")
def power_off_all():
    """Apaga todos los proyectores con IP asignada en paralelo."""
    return _bulk_power_action(turn_on=False)


def _bulk_power_action(turn_on: bool):
    """Ejecuta encendido/apagado en todos los proyectores concurrentemente."""
    rows = get_all_projectors()
    targets = [r for r in rows if r["current_ip"]]

    results = {"success": 0, "failed": 0, "total": len(targets)}

    def _action(row):
        result = send_power_command(row["current_ip"], turn_on=turn_on)
        if result["success"]:
            new_status = "warming" if turn_on else "cooling"
            update_projector_status(row["id"], new_status)
        return result["success"]

    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(_action, row) for row in targets]
        for future in as_completed(futures):
            if future.result():
                results["success"] += 1
            else:
                results["failed"] += 1

    accion = "encendido" if turn_on else "apagado"
    logger.info("Bulk %s: %d/%d exitosos", accion, results["success"], results["total"])
    return jsonify(results)


@api_bp.post("/projectors/<int:projector_id>/assign")
def assign_projector(projector_id: int):
    """
    Asigna un proyector a un aula.
    Body JSON: { "classroom_id": 5 }  — usar null para desasignar.
    """
    row = get_projector(projector_id)
    if row is None:
        return _not_found("Proyector")

    data = request.get_json(silent=True) or {}
    classroom_id = data.get("classroom_id")  # puede ser None para desasignar

    assign_projector_to_classroom(projector_id, classroom_id)
    return jsonify({
        "success": True,
        "projector_id": projector_id,
        "classroom_id": classroom_id,
    })


@api_bp.put("/projectors/<int:projector_id>/mac")
def update_mac(projector_id: int):
    """
    Actualiza la MAC address de un proyector.
    Body JSON: { "mac_address": "AA:BB:CC:DD:EE:FF" }
    """
    row = get_projector(projector_id)
    if row is None:
        return _not_found("Proyector")

    data = request.get_json(silent=True) or {}
    mac = data.get("mac_address", "").strip().upper()

    if not mac:
        return _error("Se requiere el campo 'mac_address'")

    # Verificar que la MAC no esté ya en uso por otro proyector
    existing = get_projector_by_mac(mac)
    if existing and existing["id"] != projector_id:
        return _error(f"La MAC {mac} ya está registrada en otro proyector", 409)

    update_projector_mac(projector_id, mac)
    return jsonify({"success": True, "projector_id": projector_id, "mac_address": mac})


# ---------------------------------------------------------------------------
# Escaneo — admin
# ---------------------------------------------------------------------------

@api_bp.post("/scan")
def trigger_scan():
    """
    Inicia un escaneo manual de todas las subredes configuradas.
    Puede tardar varios segundos. Retorna resumen de resultados.
    """
    logger.info("Escaneo manual iniciado desde la API")
    counters = scheduler.run_now()
    return jsonify({"success": True, **counters})


@api_bp.get("/scheduler/status")
def scheduler_status():
    """Retorna el estado del scheduler: última ejecución, intervalo, resultado."""
    return jsonify(scheduler.get_status())


@api_bp.get("/scan/log")
def scan_log():
    """Retorna el historial de eventos del escáner (últimos 100 por defecto)."""
    limit = request.args.get("limit", 100, type=int)
    rows = get_scan_log(limit=limit)
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Aulas — docentes
# ---------------------------------------------------------------------------

@api_bp.get("/classroom/<classroom_number>/info")
def classroom_info(classroom_number: str):
    """
    Retorna información del proyector asignado a un aula.
    Para uso desde la vista de docentes.
    """
    classroom = get_classroom_by_number(classroom_number)
    if classroom is None:
        return _not_found("Aula")

    projector = get_projector_by_classroom(classroom["id"])
    if projector is None:
        return jsonify({
            "classroom_number": classroom_number,
            "classroom_name": classroom["display_name"],
            "projector": None,
            "message": "No hay proyector asignado a esta aula",
        })

    return jsonify({
        "classroom_number": classroom_number,
        "classroom_name": classroom["display_name"],
        "projector": _projector_row_to_dict(projector),
    })


@api_bp.post("/classroom/<classroom_number>/power-on")
def classroom_power_on(classroom_number: str):
    """Enciende el proyector del aula indicada."""
    return _classroom_power_action(classroom_number, turn_on=True)


@api_bp.post("/classroom/<classroom_number>/power-off")
def classroom_power_off(classroom_number: str):
    """Apaga el proyector del aula indicada."""
    return _classroom_power_action(classroom_number, turn_on=False)


def _classroom_power_action(classroom_number: str, turn_on: bool):
    """
    Lógica compartida para encender/apagar por número de aula.
    """
    classroom = get_classroom_by_number(classroom_number)
    if classroom is None:
        return _not_found("Aula")

    projector = get_projector_by_classroom(classroom["id"])
    if projector is None:
        return _error("No hay proyector asignado a esta aula", 404)

    ip = projector["current_ip"]
    if not ip:
        return _error("El proyector no tiene IP asignada", 422)

    result = send_power_command(ip, turn_on=turn_on)

    if result["success"]:
        new_status = "warming" if turn_on else "cooling"
        update_projector_status(projector["id"], new_status)

    return jsonify({
        "classroom_number": classroom_number,
        "projector_id": projector["id"],
        "ip": ip,
        **result,
    })
