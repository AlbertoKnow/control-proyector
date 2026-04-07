"""
Rutas del panel de administración de ProyControl.
Protegidas con autenticación básica HTTP.
"""

import logging
from functools import wraps
from flask import Blueprint, render_template, request, Response

from config import ADMIN_USERNAME, ADMIN_PASSWORD
from models.database import (
    get_all_projectors,
    get_projector,
    get_all_campuses,
    get_classrooms,
    get_scan_log,
)

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------------------------------------------------------------------
# Autenticación básica
# ---------------------------------------------------------------------------

def _check_auth(username: str, password: str) -> bool:
    """Verifica credenciales del administrador."""
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


def _require_auth():
    """Retorna respuesta 401 con encabezado WWW-Authenticate."""
    return Response(
        "Acceso restringido. Ingrese sus credenciales.",
        401,
        {"WWW-Authenticate": 'Basic realm="ProyControl Admin"'},
    )


def login_required(f):
    """Decorador que exige autenticación básica HTTP."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not _check_auth(auth.username, auth.password):
            return _require_auth()
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

@admin_bp.get("/")
@login_required
def dashboard():
    """Panel principal: lista todos los proyectores agrupados por campus."""
    projectors = get_all_projectors()
    campuses = get_all_campuses()

    # Agrupar proyectores por campus
    grouped: dict[str, list] = {}
    for campus in campuses:
        grouped[campus["name"]] = []

    unassigned = []
    for p in projectors:
        campus_name = p["campus_name"]
        if campus_name and campus_name in grouped:
            grouped[campus_name].append(dict(p))
        else:
            unassigned.append(dict(p))

    if unassigned:
        grouped["Sin asignar"] = unassigned

    # Contadores por estado
    status_counts = {"on": 0, "off": 0, "warming": 0, "cooling": 0, "unknown": 0}
    for p in projectors:
        s = p["status"] if p["status"] in status_counts else "unknown"
        status_counts[s] += 1

    return render_template(
        "admin/dashboard.html",
        grouped=grouped,
        total=len(projectors),
        status_counts=status_counts,
    )


@admin_bp.get("/projector/<int:projector_id>")
@login_required
def projector_detail(projector_id: int):
    """Página de detalle de un proyector con controles y asignación."""
    projector = get_projector(projector_id)
    if projector is None:
        return render_template("404.html"), 404

    campuses = get_all_campuses()
    # Construir lista de aulas por campus para el selector
    classrooms_by_campus = {}
    for campus in campuses:
        classrooms_by_campus[campus["name"]] = [
            dict(c) for c in get_classrooms(campus["id"])
        ]

    log = get_scan_log(limit=20)

    return render_template(
        "admin/projector.html",
        projector=dict(projector),
        classrooms_by_campus=classrooms_by_campus,
        scan_log=[dict(e) for e in log],
    )
