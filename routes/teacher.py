"""
Rutas de la vista para docentes de ProyControl.
Sin autenticación — solo encendido/apagado por número de aula.
"""

import logging
from flask import Blueprint, render_template

from models.database import get_classroom_by_number, get_projector_by_classroom

logger = logging.getLogger(__name__)

teacher_bp = Blueprint("teacher", __name__)


@teacher_bp.get("/control/<classroom_number>")
def control(classroom_number: str):
    """
    Vista de control simple para docentes.
    Muestra dos botones: encender y apagar el proyector del aula.
    """
    classroom = get_classroom_by_number(classroom_number)

    if classroom is None:
        return render_template(
            "teacher/control.html",
            classroom_number=classroom_number,
            classroom=None,
            projector=None,
            error="Aula no encontrada",
        )

    projector = get_projector_by_classroom(classroom["id"])

    return render_template(
        "teacher/control.html",
        classroom_number=classroom_number,
        classroom=dict(classroom),
        projector=dict(projector) if projector else None,
        error=None,
    )
