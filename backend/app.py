"""QA Center: servidor de API REST (Flask) y de las vistas del frontend.

Ejecutar:  python backend/app.py   ->   http://127.0.0.1:5000
"""
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from flask import Flask, g, jsonify, redirect, render_template, request, send_file  # noqa: E402

from auth import authenticate, create_token, token_required  # noqa: E402
from automation import AutoTestScheduler, RunnerBusyError, automation_status, run_system_tests  # noqa: E402
from logger import (  # noqa: E402
    get_logger, log_failed_login, log_manual_run_registered, log_report_exported, log_successful_login,
)
from monitor import MonitorScheduler, report_extra  # noqa: E402
from qa_api import api as qa_api  # noqa: E402
from qa_store import store  # noqa: E402
from testdocs import docs  # noqa: E402
from testdocs_api import docs_api  # noqa: E402
from reports_engine import TRIGGER_MANUAL, export_report, get_dashboard_metrics, register_manual_run  # noqa: E402

FRONTEND_DIR = os.path.join(os.path.dirname(BACKEND_DIR), "frontend")
DEMO_EMAIL = "admin@test.com"
DEMO_PASSWORD = "SecurePassword123"


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(FRONTEND_DIR, "templates"),
        static_folder=os.path.join(FRONTEND_DIR, "static"),
        static_url_path="/static",
    )
    app.json.ensure_ascii = False
    app.extensions["qa_scheduler"] = None  # se asigna al iniciar el programador (ver start_scheduler)
    app.extensions["qa_monitor"] = None
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024  # importación de reportes
    app.register_blueprint(qa_api)
    app.register_blueprint(docs_api)
    get_logger()

    # ------------------------------------------------------------------ Vistas
    @app.get("/")
    def index():
        return redirect("/login")

    @app.get("/login")
    def login_page():
        # Credenciales de prueba precargadas en el formulario (QA_DEMO_LOGIN=0 lo desactiva).
        if os.environ.get("QA_DEMO_LOGIN", "1") == "0":
            return render_template("login.html", demo_email="", demo_password="")
        return render_template("login.html", demo_email=DEMO_EMAIL, demo_password=DEMO_PASSWORD)

    @app.get("/dashboard")
    def dashboard_page():
        # La protección de la ruta se hace en el cliente (token en localStorage);
        # los datos solo se entregan a través de endpoints protegidos con JWT.
        return render_template("dashboard.html")

    # ------------------------------------------------------------------ API
    @app.post("/api/v1/auth/login")
    def api_login():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"error": "El cuerpo de la petición debe ser JSON"}), 400
        email = str(data.get("email") or "").strip()
        password = str(data.get("password") or "")
        if not email or not password:
            return jsonify({"error": "Email y contraseña son obligatorios"}), 400

        user = authenticate(email, password)
        if user is None:
            log_failed_login(email, request.remote_addr)
            return jsonify({"error": "Credenciales inválidas"}), 401

        log_successful_login(email, request.remote_addr)
        return jsonify({"token": create_token(email, user), "user": user}), 200

    @app.get("/api/v1/dashboard/metrics")
    @token_required
    def api_metrics():
        metrics = get_dashboard_metrics()
        metrics["automation"] = automation_status(app.extensions["qa_scheduler"])
        metrics["incidents"] = store.incident_summary()
        metrics["scans"] = store.scan_summary()
        metrics["docs"] = docs.plan_summary()
        return jsonify(metrics), 200

    @app.post("/api/v1/test-runs/execute")
    @token_required
    def api_execute_tests():
        try:
            result = run_system_tests(app, executed_by=g.current_user.get("name", g.current_user["sub"]),
                                      trigger=TRIGGER_MANUAL)
        except RunnerBusyError as exc:
            return jsonify({"error": str(exc)}), 409
        return jsonify(result), 200

    @app.post("/api/v1/test-runs")
    @token_required
    def api_register_run():
        try:
            run = register_manual_run(request.get_json(silent=True),
                                      executed_by=g.current_user.get("name", g.current_user["sub"]))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        log_manual_run_registered(run["run_id"], run["suite"], g.current_user["sub"])
        return jsonify(run), 201

    @app.get("/api/v1/reports/export")
    @token_required
    def api_export():
        report_format = request.args.get("format", "")
        try:
            buffer, mimetype, filename = export_report(report_format, report_extra())
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        log_report_exported(report_format, g.current_user["sub"])
        return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=filename, max_age=0)

    @app.get("/api/v1/health")
    def api_health():
        return jsonify({"status": "ok"}), 200

    # ------------------------------------------------------------------ Errores
    @app.errorhandler(404)
    def not_found(_err):
        if request.path.startswith("/api/"):
            return jsonify({"error": "Recurso no encontrado"}), 404
        return redirect("/login")

    @app.errorhandler(405)
    def method_not_allowed(_err):
        return jsonify({"error": "Método no permitido"}), 405

    return app


def start_scheduler(flask_app: Flask) -> None:
    """Inicia las pruebas automáticas periódicas (QA_AUTO_RUN_MINUTES=0 las desactiva) y el monitoreo
    de aplicaciones (QA_MONITOR=0 lo desactiva)."""
    store.mark_stale_scans()
    interval = float(os.environ.get("QA_AUTO_RUN_MINUTES", "5"))
    if interval > 0 and flask_app.extensions["qa_scheduler"] is None:
        scheduler = AutoTestScheduler(flask_app, interval)
        flask_app.extensions["qa_scheduler"] = scheduler
        scheduler.start()
    if os.environ.get("QA_MONITOR", "1") != "0" and flask_app.extensions["qa_monitor"] is None:
        monitor_scheduler = MonitorScheduler()
        flask_app.extensions["qa_monitor"] = monitor_scheduler
        monitor_scheduler.start()


app = create_app()

if __name__ == "__main__":
    # Con el recargador de debug el script corre dos veces; el programador solo inicia en el proceso hijo.
    if os.environ.get("FLASK_DEBUG") != "1" or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_scheduler(app)
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
