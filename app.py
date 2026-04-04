"""
Punto de entrada de ProyControl UTP.
Inicializa Flask, la base de datos, los blueprints y el scheduler.
"""

import logging
from flask import Flask, redirect, url_for

from config import SECRET_KEY, DEBUG
from models.database import init_db
from routes.api import api_bp
from routes.admin import admin_bp
from routes.teacher import teacher_bp
from services.scheduler import scheduler

# --- Logging ---
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """
    Fábrica de la aplicación Flask.
    Registra blueprints, prepara la BD e inicia el scheduler.
    """
    app = Flask(__name__)
    app.secret_key = SECRET_KEY

    # Inicializar base de datos (crea tablas si no existen)
    init_db()

    # Registrar blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(teacher_bp)

    # Ruta raíz → redirige al panel admin
    @app.get("/")
    def index():
        return redirect(url_for("admin.dashboard"))

    # Iniciar escaneo periódico automático
    # use_reloader=True lanza dos procesos en debug → evitar doble scheduler
    import os
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        scheduler.start()

    logger.info("ProyControl UTP iniciado")
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=DEBUG)
