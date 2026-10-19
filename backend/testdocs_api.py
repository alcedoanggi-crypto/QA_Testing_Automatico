"""API REST de Documentación QA: planes, requisitos, casos de prueba (con ejecución y evidencias),
matriz de trazabilidad y reporte de defectos. Todas las rutas exigen JWT."""
import io

from flask import Blueprint, g, jsonify, request, send_file

from auth import token_required
from logger import get_logger
from qa_store import PRIORITIES, NotFoundError, SEVERITIES, store
from reports_engine import ENVIRONMENTS, TOOLS
from testdocs import CASE_STATUSES, CASE_TYPES, PLAN_STATUSES, REQUIREMENT_KINDS, docs
from testdocs_reports import case_report, cases_report, defect_report, defects_report, plan_report, rtm_report

docs_api = Blueprint("docs_api", __name__, url_prefix="/api/v1")


def user_name():
    return g.current_user.get("name", g.current_user["sub"])


def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ValueError("El cuerpo de la petición debe ser JSON")
    return data


def report_format():
    fmt = request.args.get("format", "pdf")
    if fmt not in ("pdf", "excel"):
        raise ValueError("Formato no soportado. Use pdf o excel.")
    return fmt


def send_report(result):
    buffer, mimetype, filename = result
    get_logger().info("DOCUMENTO_QA_EXPORTADO - %s | Usuario: %s", filename, g.current_user["sub"])
    return send_file(buffer, mimetype=mimetype, as_attachment=True, download_name=filename, max_age=0)


@docs_api.errorhandler(ValueError)
def handle_value_error(exc):
    return jsonify({"error": str(exc)}), 400


@docs_api.errorhandler(NotFoundError)
def handle_not_found(exc):
    return jsonify({"error": str(exc)}), 404


@docs_api.get("/docs/catalogs")
@token_required
def doc_catalogs():
    return jsonify({"plan_statuses": PLAN_STATUSES, "case_statuses": CASE_STATUSES, "case_types": CASE_TYPES,
                    "requirement_kinds": REQUIREMENT_KINDS, "priorities": PRIORITIES, "severities": SEVERITIES,
                    "environments": ENVIRONMENTS, "tools": TOOLS})


@docs_api.get("/docs/summary")
@token_required
def doc_summary():
    summary = docs.plan_summary()
    summary["plans"] = len(docs.list_plans())
    return jsonify(summary)


# ----------------------------------------------------------------------------- planes
@docs_api.get("/plans")
@token_required
def list_plans():
    return jsonify(docs.list_plans())


@docs_api.post("/plans")
@token_required
def create_plan():
    return jsonify(docs.create_plan(body())), 201


@docs_api.get("/plans/<int:plan_id>")
@token_required
def get_plan(plan_id):
    return jsonify(docs.get_plan(plan_id))


@docs_api.put("/plans/<int:plan_id>")
@token_required
def update_plan(plan_id):
    return jsonify(docs.update_plan(plan_id, body()))


@docs_api.delete("/plans/<int:plan_id>")
@token_required
def delete_plan(plan_id):
    docs.delete_plan(plan_id)
    return jsonify({"deleted": plan_id})


@docs_api.get("/plans/<int:plan_id>/report")
@token_required
def plan_document(plan_id):
    fmt = report_format()
    plan = docs.get_plan(plan_id)
    specs = [docs.get_spec(s["id"], full=True) for s in docs.list_specs({"plan_id": plan_id})]
    return send_report(plan_report(plan, specs, docs.traceability(plan_id), fmt))


# ----------------------------------------------------------------------------- requisitos
@docs_api.get("/requirements")
@token_required
def list_requirements():
    return jsonify(docs.list_requirements(request.args.get("plan_id") or None))


@docs_api.post("/requirements")
@token_required
def create_requirement():
    return jsonify(docs.create_requirement(body())), 201


@docs_api.put("/requirements/<int:req_id>")
@token_required
def update_requirement(req_id):
    return jsonify(docs.update_requirement(req_id, body()))


@docs_api.delete("/requirements/<int:req_id>")
@token_required
def delete_requirement(req_id):
    docs.delete_requirement(req_id)
    return jsonify({"deleted": req_id})


# ----------------------------------------------------------------------------- casos de prueba
@docs_api.get("/test-cases")
@token_required
def list_specs():
    return jsonify(docs.list_specs(request.args.to_dict()))


@docs_api.post("/test-cases")
@token_required
def create_spec():
    return jsonify(docs.create_spec(body(), user_name())), 201


@docs_api.get("/test-cases/report")
@token_required
def specs_document():
    fmt = report_format()
    filters = {k: v for k, v in request.args.items() if k != "format"}
    specs = [docs.get_spec(s["id"], full=True) for s in docs.list_specs(filters)]
    title = "Casos de prueba"
    if filters.get("plan_id"):
        plan = docs.get_plan(int(filters["plan_id"]))
        title += f" · {plan['code']} {plan['name']}"
    return send_report(cases_report(specs, fmt, title, docs.evidence_dir))


@docs_api.get("/test-cases/<int:spec_id>")
@token_required
def get_spec(spec_id):
    return jsonify(docs.get_spec(spec_id, full=True))


@docs_api.put("/test-cases/<int:spec_id>")
@token_required
def update_spec(spec_id):
    return jsonify(docs.update_spec(spec_id, body()))


@docs_api.delete("/test-cases/<int:spec_id>")
@token_required
def delete_spec(spec_id):
    docs.delete_spec(spec_id)
    return jsonify({"deleted": spec_id})


@docs_api.post("/test-cases/<int:spec_id>/duplicate")
@token_required
def duplicate_spec(spec_id):
    return jsonify(docs.duplicate_spec(spec_id, user_name())), 201


@docs_api.get("/test-cases/<int:spec_id>/report")
@token_required
def spec_document(spec_id):
    return send_report(case_report(docs.get_spec(spec_id, full=True), report_format(), docs.evidence_dir))


@docs_api.post("/test-cases/<int:spec_id>/execute")
@token_required
def execute_spec(spec_id):
    """Registra el resultado. Si falla y se pide, crea el defecto (novedad) con los datos del caso."""
    data = body()
    spec = docs.get_spec(spec_id)
    incident = None
    if data.get("status") == "Fallido" and data.get("create_defect"):
        if spec.get("incident_id") and spec.get("incident_status") not in ("Cerrada", "Verificada", None):
            incident = store.register_occurrence(spec["incident_id"], f"El caso {spec['code']} volvió a fallar",
                                                 user_name())
        else:
            actual = str(data.get("actual") or "").strip()
            incident = store.create_incident({
                "title": f"[{spec['code']}] {spec['title']}"[:200],
                "description": spec["description"] or f"Falla detectada al ejecutar el caso de prueba {spec['code']}.",
                "steps": "\n".join(filter(None, [
                    f"Precondiciones: {spec['preconditions']}" if spec["preconditions"] else "",
                    f"Datos de entrada: {spec['input_data']}" if spec["input_data"] else "", spec["steps"]])),
                "expected": spec["expected"], "actual": actual or "El resultado no coincide con lo esperado.",
                "severity": data.get("severity") or "Media", "priority": data.get("priority") or "Normal",
                "module": spec["module"], "url": spec["url"], "environment": spec["environment"],
                "developer_id": data.get("developer_id") or None,
            }, user_name(), source="Caso de prueba", source_ref=spec["code"])
    result = docs.record_execution(spec_id, data, user_name(), incident["id"] if incident else None)
    get_logger().info("CASO_EJECUTADO - %s | Resultado: %s | Defecto: %s | Usuario: %s", spec["code"],
                      result["status"], incident["code"] if incident else "-", g.current_user["sub"])
    return jsonify({**result, "defect": incident})


@docs_api.post("/test-cases/<int:spec_id>/evidence")
@token_required
def upload_evidence(spec_id):
    files = request.files.getlist("file")
    if not files:
        raise ValueError("Adjunta al menos un archivo")
    saved = [docs.add_evidence(spec_id, f.filename, f.read(), f.mimetype, user_name()) for f in files]
    return jsonify([{k: v for k, v in ev.items() if k != "path"} for ev in saved]), 201


@docs_api.get("/evidence/<int:ev_id>")
@token_required
def download_evidence(ev_id):
    ev = docs.get_evidence(ev_id)
    inline = request.args.get("inline") == "1" and ev["mimetype"].startswith("image/")
    try:
        # Se lee en memoria (máx. 10 MB) para no dejar el archivo bloqueado en Windows y poder eliminarlo luego.
        with open(ev["path"], "rb") as fh:
            data = io.BytesIO(fh.read())
    except FileNotFoundError:
        raise NotFoundError("El archivo de la evidencia ya no existe") from None
    return send_file(data, mimetype=ev["mimetype"], as_attachment=not inline, download_name=ev["filename"], max_age=0)


@docs_api.delete("/evidence/<int:ev_id>")
@token_required
def delete_evidence(ev_id):
    docs.delete_evidence(ev_id)
    return jsonify({"deleted": ev_id})


# ----------------------------------------------------------------------------- trazabilidad
@docs_api.get("/rtm")
@token_required
def traceability():
    return jsonify(docs.traceability(request.args.get("plan_id") or None))


@docs_api.get("/rtm/report")
@token_required
def traceability_document():
    plan_id = request.args.get("plan_id") or None
    plan = docs.get_plan(int(plan_id)) if plan_id else None
    return send_report(rtm_report(docs.traceability(plan_id), report_format(), plan))


# ----------------------------------------------------------------------------- reporte de defectos
@docs_api.get("/defects/report")
@token_required
def defects_document():
    filters = {k: v for k, v in request.args.items() if k != "format"}
    incidents = store.list_incidents({**filters, "order": "severity"})
    return send_report(defects_report(incidents, report_format()))


@docs_api.get("/incidents/<int:incident_id>/report")
@token_required
def defect_document(incident_id):
    return send_report(defect_report(store.get_incident(incident_id, with_history=True), report_format()))
