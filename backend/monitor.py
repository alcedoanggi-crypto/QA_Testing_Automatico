"""Orquestación de análisis de URL, creación automática de novedades y monitoreo periódico de aplicaciones."""
import datetime as dt
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from logger import get_logger
from notifier import NotificationError, available_channels, notify_incident, send_email
from reports_engine import export_report
from qa_store import NotFoundError, issue_fingerprint, store
from url_scanner import scan_url

SYSTEM_USER = "Sistema automático"
TRIGGER_MANUAL = "Manual"
TRIGGER_MONITOR = "Monitoreo"
SOURCE_LABELS = {"console": "Consola", "javascript": "JavaScript", "network": "Red", "navegador": "Navegador"}

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="qa-scan")


# ----------------------------------------------------------------------------- notificaciones
def send_incident(incident_id, channels, note, author) -> dict:
    """Envía la novedad al programador y lo deja en el historial."""
    incident = store.get_incident(incident_id)
    settings = store.get_settings(include_secrets=True)
    results = notify_incident(incident, settings, channels, note)
    sent = [c for c, r in results.items() if r == "ok"]
    failed = {c: r for c, r in results.items() if r != "ok"}
    labels = {"email": "correo", "webhook": "webhook"}
    if sent:
        store.mark_notified(incident_id)
        destination = f" a {incident['developer_name']}" if incident.get("developer_name") else ""
        store.add_history(incident_id, "Notificación",
                          f"Enviada{destination} por {', '.join(labels[c] for c in sent)}"
                          + (f". Nota: {note}" if note else ""), author)
        if incident["status"] == "Nueva" and incident.get("developer_id"):
            store.update_incident(incident_id, {"status": "Asignada"}, author)
    for channel, error in failed.items():
        store.add_history(incident_id, "Error de envío", f"{labels.get(channel, channel)}: {error}", author)
    return results


def record_manual_share(incident_id, channel, author) -> dict:
    """Registra que QA compartió la novedad por un medio externo (correo propio, copiar texto…)."""
    incident = store.get_incident(incident_id)
    store.mark_notified(incident_id)
    who = f" con {incident['developer_name']}" if incident.get("developer_name") else ""
    return store.add_history(incident_id, "Notificación", f"Compartida{who} ({channel})", author)


# ----------------------------------------------------------------------------- novedades desde errores
def _severity_for(issue) -> str:
    message = issue["message"]
    if issue["source"] == "javascript":
        return "Alta"
    if issue["source"] == "network":
        if "HTTP 5" in message or "Document" in message or "No hay conexión" in message:
            return "Alta"
        return "Media" if issue["level"] == "error" else "Baja"
    return "Media" if issue["level"] == "error" else "Baja"


def incident_from_issue(issue, scan) -> dict:
    first_line = issue["message"].strip().splitlines()[0] if issue["message"].strip() else "Error sin mensaje"
    label = SOURCE_LABELS.get(issue["source"], issue["source"])
    actual = issue["message"]
    if issue.get("resource_url"):
        actual += f"\nRecurso: {issue['resource_url']}"
    if issue.get("location"):
        actual += f"\nUbicación: {issue['location']}"
    page = issue.get("page_url") or scan["url"]
    return {
        "title": f"[{label}] {first_line}"[:200],
        "description": f"Error detectado automáticamente al analizar {page} ({scan['scan_id']}, {scan['engine']}).",
        "steps": f"1. Abrir {page}\n2. Abrir las herramientas de desarrollo (F12) > pestaña "
                 f"{'Red' if issue['source'] == 'network' else 'Consola'}\n3. Recargar la página y observar el mensaje",
        "expected": "La página carga sin errores en la consola ni peticiones fallidas.",
        "actual": actual,
        "severity": _severity_for(issue),
        "priority": "Alta" if _severity_for(issue) in ("Crítica", "Alta") else "Normal",
        "url": page,
        "environment": scan.get("environment") or "Local",
        "module": scan.get("target_name") or "",
    }


def create_incidents_from_issues(scan_id, issue_ids, author, developer_id=None, notify=False,
                                 source="Análisis de URL") -> dict:
    """Convierte errores de un análisis en novedades. Si ya existe una abierta con la misma huella,
    suma una reaparición en lugar de duplicarla."""
    scan = store.get_scan(scan_id)
    if scan.get("target_id"):
        try:
            target = store.get_target(scan["target_id"])
            scan["environment"] = target["environment"]
            if developer_id is None:
                developer_id = target.get("developer_id")
        except NotFoundError:
            pass
    created, repeated = [], []
    for issue in store.get_scan_issues(scan_id, issue_ids):
        if issue.get("incident_id"):
            continue
        existing = store.find_open_incident_by_fingerprint(issue["fingerprint"])
        if existing:
            store.register_occurrence(existing["id"], f"Detectada de nuevo en {scan_id}", author)
            store.link_issue(issue["id"], existing["id"])
            repeated.append(existing["code"])
            continue
        data = incident_from_issue(issue, scan)
        data["developer_id"] = developer_id
        incident = store.create_incident(data, author, source=source, source_ref=scan_id,
                                         fingerprint=issue["fingerprint"])
        store.link_issue(issue["id"], incident["id"])
        created.append(incident)
    notified = []
    if notify:
        channels = available_channels(store.get_settings(include_secrets=True))
        for incident in created:
            if channels and incident.get("developer_id"):
                send_incident(incident["id"], channels, "", author)
                notified.append(incident["code"])
    return {"created": created, "repeated": repeated, "notified": notified}


def create_incidents_from_run(run, cases, author, developer_id=None) -> list:
    """Una novedad por cada caso fallido de una ejecución (importada o registrada)."""
    created = []
    for case in cases:
        if case["status"] != "Failed":
            continue
        fingerprint = issue_fingerprint(run.get("url") or run["suite"], "test", case["name"])
        existing = store.find_open_incident_by_fingerprint(fingerprint)
        if existing:
            store.register_occurrence(existing["id"], f"Falló de nuevo en {run['run_id']}", author)
            continue
        created.append(store.create_incident({
            "title": f"[{run['tool']}] Falla: {case['name']}"[:200],
            "description": f"Caso fallido en la suite «{run['suite']}» ({run['run_id']}, {run['tool']}).",
            "actual": case.get("detail") or "El caso de prueba falló.",
            "expected": "El caso de prueba pasa.",
            "severity": "Media", "priority": "Normal",
            "environment": run["environment"], "module": run.get("module") or run["suite"],
            "url": run.get("url") or "", "developer_id": developer_id,
        }, author, source="Resultado de pruebas", source_ref=run["run_id"], fingerprint=fingerprint))
    return created


# ----------------------------------------------------------------------------- análisis
def _run_scan(scan_id, url, max_pages, wait_seconds, auto_incidents, author):
    log = get_logger()
    try:
        screenshot = os.path.join(store.screenshots_dir, f"{scan_id}.png")
        result = scan_url(url, max_pages=max_pages, wait_seconds=wait_seconds, screenshot_path=screenshot)
        scan = store.finish_scan(scan_id, result, result.get("issues", []))
    except Exception as exc:  # nunca dejar un análisis "En curso"
        log.error("ERROR_ANALISIS_URL - %s | %s | %r", scan_id, url, exc)
        return store.finish_scan(scan_id, {"status": "Error", "message": f"Error inesperado: {exc}"}, [])
    level = log.warning if scan["errors"] or scan["network_errors"] else log.info
    level("ANALISIS_URL_FINALIZADO - %s | %s | Errores: %d | Red: %d | Advertencias: %d", scan_id, url,
          scan["errors"], scan["network_errors"], scan["warnings"])
    if auto_incidents and scan["status"] != "Error":
        settings = store.get_settings()
        levels = {"error"} | ({"warning"} if settings.get("auto_incident_warnings") == "1" else set())
        ids = [i["id"] for i in store.get_scan_issues(scan_id) if i["level"] in levels]
        if ids:
            summary = create_incidents_from_issues(scan_id, ids, SYSTEM_USER,
                                                   notify=settings.get("auto_notify") == "1")
            if summary["created"] or summary["repeated"]:
                log.warning("NOVEDADES_AUTOMATICAS - %s | Nuevas: %d | Repetidas: %d", scan_id,
                            len(summary["created"]), len(summary["repeated"]))
    return store.get_scan(scan_id)


def start_scan(url, executed_by, target_id=None, max_pages=1, wait_seconds=None, trigger=TRIGGER_MANUAL,
               auto_incidents=None, wait=False) -> dict:
    settings = store.get_settings()
    if wait_seconds is None:
        wait_seconds = float(settings.get("scan_wait_seconds") or 2)
    if auto_incidents is None:
        auto_incidents = settings.get("auto_incidents") == "1"
    scan = store.create_scan(url, target_id, executed_by, trigger)
    get_logger().info("ANALISIS_URL_INICIADO - %s | %s | Por: %s", scan["scan_id"], url, executed_by)
    args = (scan["scan_id"], url, max_pages, wait_seconds, auto_incidents, executed_by)
    if wait:
        return _run_scan(*args)
    _executor.submit(_run_scan, *args)
    return scan


# ----------------------------------------------------------------------------- reportes automáticos
def report_extra() -> dict:
    """Secciones de novedades y análisis de URL que se agregan al reporte ejecutivo."""
    return {"incidents_list": store.list_incidents(), "scans_list": store.list_scans(50)}


def generate_auto_report(author=SYSTEM_USER, send=True) -> dict:
    """Genera el reporte ejecutivo (PDF + Excel), lo guarda en data/reportes y lo envía por correo si hay
    destinatarios y SMTP configurados."""
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    extra = report_extra()
    files = []
    for fmt, ext, mimetype in (("pdf", "pdf", "application/pdf"),
                               ("excel", "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")):
        buffer, _, _ = export_report(fmt, extra)
        name = f"reporte_qa_{stamp}.{ext}"
        data = buffer.getvalue()
        with open(os.path.join(store.reports_dir, name), "wb") as fh:
            fh.write(data)
        files.append((name, data, mimetype))
    settings = store.get_settings(include_secrets=True)
    open_incidents = [i for i in extra["incidents_list"] if i["status"] in ("Nueva", "Asignada", "En progreso",
                                                                            "Reabierta")]
    result = {"files": [f[0] for f in files], "emailed_to": "", "email_error": ""}
    recipients = settings.get("report_recipients", "").strip()
    if send and recipients:
        body = (f"Reporte automático de QA Center ({stamp.replace('_', ' ')}).\n\n"
                f"Novedades abiertas: {len(open_incidents)} de {len(extra['incidents_list'])}\n"
                f"Análisis de URL registrados: {len(extra['scans_list'])}\n\n"
                "Se adjunta el informe ejecutivo en PDF y el detalle en Excel.")
        try:
            send_email(settings, recipients, f"Reporte QA Center {stamp[:10]}", body, files)
            result["emailed_to"] = recipients
        except NotificationError as exc:
            result["email_error"] = str(exc)
    store.update_settings({"report_last_date": dt.date.today().isoformat()})
    get_logger().info("REPORTE_AUTOMATICO_GENERADO - %s | Por: %s | Enviado a: %s", ", ".join(result["files"]),
                      author, result["emailed_to"] or result["email_error"] or "nadie")
    return result


def list_auto_reports() -> list:
    reports = []
    for name in sorted(os.listdir(store.reports_dir), reverse=True):
        path = os.path.join(store.reports_dir, name)
        if os.path.isfile(path):
            reports.append({"name": name, "size": os.path.getsize(path),
                            "created_at": dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")})
    return reports


def daily_report_due(now=None) -> bool:
    now = now or dt.datetime.now()
    settings = store.get_settings()
    hour = settings.get("report_hour", "")
    return hour.isdigit() and now.hour >= int(hour) and settings.get("report_last_date") != now.date().isoformat()


# ----------------------------------------------------------------------------- monitoreo
class MonitorScheduler:
    """Analiza las aplicaciones marcadas con «Monitorear» cada N minutos (configurable en pantalla)."""

    TICK_SECONDS = 20

    def __init__(self, initial_delay_seconds=30):
        self.next_run_at = dt.datetime.now() + dt.timedelta(seconds=initial_delay_seconds)
        self.last_run_at = None
        self.running = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="qa-monitor", daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=10)

    def interval_minutes(self) -> float:
        try:
            return max(1.0, float(store.setting("monitor_interval_minutes") or 30))
        except ValueError:
            return 30.0

    def run_now(self):
        self.next_run_at = dt.datetime.now()

    def _loop(self):
        while not self._stop.wait(self.TICK_SECONDS):
            try:
                if daily_report_due():
                    generate_auto_report()
            except Exception as exc:
                get_logger().error("ERROR_REPORTE_AUTOMATICO - %r", exc)
            if dt.datetime.now() < self.next_run_at:
                continue
            self.running = True
            try:
                for target in store.monitored_targets():
                    if self._stop.is_set():
                        break
                    start_scan(target["url"], SYSTEM_USER, target_id=target["id"], max_pages=target["max_pages"],
                               trigger=TRIGGER_MONITOR, wait=True)
            except Exception as exc:
                get_logger().error("ERROR_MONITOREO - %r", exc)
            finally:
                self.running = False
                self.last_run_at = dt.datetime.now()
                self.next_run_at = self.last_run_at + dt.timedelta(minutes=self.interval_minutes())

    def status(self) -> dict:
        return {
            "enabled": True,
            "interval_minutes": self.interval_minutes(),
            "next_run_at": self.next_run_at.strftime("%Y-%m-%d %H:%M:%S"),
            "last_run_at": self.last_run_at.strftime("%Y-%m-%d %H:%M:%S") if self.last_run_at else None,
            "running": self.running,
            "targets": len(store.monitored_targets()),
        }
