"""Almacén SQLite de programadores, aplicaciones monitoreadas, análisis de URL, novedades y configuración.

Comparte el archivo de base de datos con ``reports_engine`` (ejecuciones de pruebas).
"""
import hashlib
import os
import re
import sqlite3
import threading
from contextlib import contextmanager
from urllib.parse import urlsplit

from reports_engine import DEFAULT_DB_PATH, ENVIRONMENTS, now_str

SEVERITIES = ["Crítica", "Alta", "Media", "Baja"]
PRIORITIES = ["Urgente", "Alta", "Normal", "Baja"]
INCIDENT_STATUSES = ["Nueva", "Asignada", "En progreso", "Resuelta", "Verificada", "Cerrada", "Reabierta"]
OPEN_STATUSES = ["Nueva", "Asignada", "En progreso", "Reabierta"]
INCIDENT_SOURCES = ["Manual", "Análisis de URL", "Resultado de pruebas", "Caso de prueba", "Pruebas automáticas"]

DEFAULT_SETTINGS = {
    "monitor_interval_minutes": "30",
    "auto_incidents": "1",           # crear novedades a partir de errores detectados
    "auto_incident_warnings": "0",   # también para advertencias de consola
    "auto_notify": "0",              # notificar al programador al crear la novedad automáticamente
    "scan_wait_seconds": "2",
    "webhook_url": "",
    "smtp_host": "",
    "smtp_port": "587",
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": "",
    "smtp_tls": "1",
    "public_base_url": "http://127.0.0.1:5000",
    "report_hour": "18",             # hora (0-23) del reporte automático diario; vacío = desactivado
    "report_recipients": "",         # correos separados por coma que reciben el reporte
    "report_last_date": "",          # uso interno: último día en que se generó
}
SECRET_SETTINGS = {"smtp_password"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS developers (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL,
    area        TEXT NOT NULL DEFAULT '',
    phone       TEXT NOT NULL DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS targets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    url           TEXT NOT NULL,
    environment   TEXT NOT NULL,
    developer_id  INTEGER,
    monitor       INTEGER NOT NULL DEFAULT 0,
    max_pages     INTEGER NOT NULL DEFAULT 1,
    notes         TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS scans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id         TEXT UNIQUE,
    target_id       INTEGER,
    url             TEXT NOT NULL,
    status          TEXT NOT NULL,
    engine          TEXT NOT NULL DEFAULT '',
    http_status     INTEGER,
    load_ms         REAL,
    page_title      TEXT NOT NULL DEFAULT '',
    pages_scanned   INTEGER NOT NULL DEFAULT 0,
    errors          INTEGER NOT NULL DEFAULT 0,
    warnings        INTEGER NOT NULL DEFAULT 0,
    network_errors  INTEGER NOT NULL DEFAULT 0,
    message         TEXT NOT NULL DEFAULT '',
    has_screenshot  INTEGER NOT NULL DEFAULT 0,
    executed_by     TEXT NOT NULL,
    "trigger"       TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT
);
CREATE TABLE IF NOT EXISTS scan_issues (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id      TEXT NOT NULL,
    level        TEXT NOT NULL,
    source       TEXT NOT NULL,
    message      TEXT NOT NULL,
    page_url     TEXT NOT NULL DEFAULT '',
    resource_url TEXT NOT NULL DEFAULT '',
    location     TEXT NOT NULL DEFAULT '',
    fingerprint  TEXT NOT NULL,
    incident_id  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_scan_issues_scan ON scan_issues (scan_id);
CREATE TABLE IF NOT EXISTS incidents (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT UNIQUE,
    title         TEXT NOT NULL,
    description   TEXT NOT NULL DEFAULT '',
    steps         TEXT NOT NULL DEFAULT '',
    expected      TEXT NOT NULL DEFAULT '',
    actual        TEXT NOT NULL DEFAULT '',
    severity      TEXT NOT NULL,
    priority      TEXT NOT NULL,
    status        TEXT NOT NULL,
    module        TEXT NOT NULL DEFAULT '',
    url           TEXT NOT NULL DEFAULT '',
    environment   TEXT NOT NULL DEFAULT 'QA',
    developer_id  INTEGER,
    source        TEXT NOT NULL DEFAULT 'Manual',
    source_ref    TEXT NOT NULL DEFAULT '',
    fingerprint   TEXT NOT NULL DEFAULT '',
    occurrences   INTEGER NOT NULL DEFAULT 1,
    due_date      TEXT NOT NULL DEFAULT '',
    reported_by   TEXT NOT NULL,
    notified_at   TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incidents_fingerprint ON incidents (fingerprint);
CREATE TABLE IF NOT EXISTS incident_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id  INTEGER NOT NULL,
    kind         TEXT NOT NULL,
    detail       TEXT NOT NULL,
    author       TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_incident_history ON incident_history (incident_id);
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class NotFoundError(LookupError):
    """El recurso solicitado no existe."""


# ----------------------------------------------------------------------------- utilidades
def clean_text(data: dict, key: str, label: str, max_len: int, required=False) -> str:
    value = str((data or {}).get(key) or "").strip()
    if required and not value:
        raise ValueError(f"El campo '{label}' es obligatorio")
    if len(value) > max_len:
        raise ValueError(f"El campo '{label}' admite máximo {max_len} caracteres")
    return value


def clean_choice(data: dict, key: str, label: str, choices: list, default: str) -> str:
    value = str((data or {}).get(key) or default).strip()
    if value not in choices:
        raise ValueError(f"{label} inválido. Use: {', '.join(choices)}")
    return value


def clean_url(value: str, required=True) -> str:
    url = str(value or "").strip()
    if not url:
        if required:
            raise ValueError("La URL es obligatoria")
        return ""
    invalid = ValueError("URL inválida. Ejemplo: http://localhost:3000")
    if re.search(r"\s", url):
        raise invalid
    if "://" not in url:
        # "localhost:3000" es válido; "javascript:..." o "mailto:..." no.
        if re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", url, re.IGNORECASE):
            raise invalid
        url = "http://" + url
    parts = urlsplit(url)
    try:
        parts.port  # valida el puerto
    except ValueError:
        raise invalid from None
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise invalid
    if len(url) > 500:
        raise ValueError("La URL admite máximo 500 caracteres")
    return url


def issue_fingerprint(page_url: str, source: str, message: str) -> str:
    """Huella para no duplicar novedades: misma página, mismo origen y mismo mensaje (sin números)."""
    parts = urlsplit(page_url or "")
    page = f"{parts.netloc}{parts.path}"
    normalized = re.sub(r"\d+", "#", re.sub(r"\?[^\s'\"]*", "", (message or "").lower())).strip()
    return hashlib.sha1(f"{page}|{source}|{normalized}".encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------- almacén
class QAStore:
    __test__ = False

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        with self._connection() as conn:
            conn.executescript(SCHEMA)

    @property
    def screenshots_dir(self) -> str:
        path = os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "screenshots")
        os.makedirs(path, exist_ok=True)
        return path

    @property
    def reports_dir(self) -> str:
        path = os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "reportes")
        os.makedirs(path, exist_ok=True)
        return path

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _all(self, sql, params=()):
        with self._connection() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def _one(self, sql, params=()):
        rows = self._all(sql, params)
        return rows[0] if rows else None

    # ------------------------------------------------------------------ configuración
    def get_settings(self, include_secrets=False) -> dict:
        values = dict(DEFAULT_SETTINGS)
        values.update({r["key"]: r["value"] for r in self._all("SELECT key, value FROM settings")})
        if not include_secrets:
            for key in SECRET_SETTINGS:
                values[key + "_set"] = bool(values.get(key))
                values[key] = ""
        return values

    def setting(self, key: str) -> str:
        return self.get_settings(include_secrets=True).get(key, "")

    def update_settings(self, data: dict) -> dict:
        if not isinstance(data, dict):
            raise ValueError("El cuerpo de la petición debe ser JSON")
        updates = {}
        for key, value in data.items():
            if key not in DEFAULT_SETTINGS:
                continue
            value = "" if value is None else str(value).strip()
            if key in SECRET_SETTINGS and value == "":
                continue  # vacío = conservar la contraseña guardada
            if isinstance(data[key], bool):
                value = "1" if data[key] else "0"
            updates[key] = value
        interval = updates.get("monitor_interval_minutes")
        if interval is not None:
            try:
                if not 1 <= float(interval) <= 1440:
                    raise ValueError
            except ValueError:
                raise ValueError("El intervalo de monitoreo debe estar entre 1 y 1440 minutos") from None
        wait = updates.get("scan_wait_seconds")
        if wait is not None:
            try:
                if not 0 <= float(wait) <= 30:
                    raise ValueError
            except ValueError:
                raise ValueError("La espera tras cargar la página debe estar entre 0 y 30 segundos") from None
        if updates.get("webhook_url"):
            clean_url(updates["webhook_url"])
        hour = updates.get("report_hour")
        if hour and not (hour.isdigit() and 0 <= int(hour) <= 23):
            raise ValueError("La hora del reporte diario debe estar entre 0 y 23 (vacío = desactivado)")
        for email in filter(None, (e.strip() for e in updates.get("report_recipients", "").split(","))):
            if not EMAIL_PATTERN.match(email):
                raise ValueError(f"Correo inválido en destinatarios del reporte: {email}")
        if updates.get("smtp_port"):
            if not updates["smtp_port"].isdigit():
                raise ValueError("El puerto SMTP debe ser numérico")
        with self._lock, self._connection() as conn:
            conn.executemany("INSERT INTO settings (key, value) VALUES (?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value = excluded.value", list(updates.items()))
        return self.get_settings()

    # ------------------------------------------------------------------ programadores
    DEV_SQL = """
        SELECT d.*, (SELECT COUNT(*) FROM incidents i WHERE i.developer_id = d.id
                     AND i.status IN ({open})) AS open_incidents,
                    (SELECT COUNT(*) FROM incidents i WHERE i.developer_id = d.id) AS total_incidents
        FROM developers d
    """.format(open=", ".join(f"'{s}'" for s in OPEN_STATUSES))

    def list_developers(self) -> list:
        return self._all(self.DEV_SQL + " ORDER BY d.active DESC, d.name")

    def get_developer(self, dev_id) -> dict:
        dev = self._one(self.DEV_SQL + " WHERE d.id = ?", (dev_id,))
        if dev is None:
            raise NotFoundError("Programador no encontrado")
        return dev

    def _validate_developer(self, data):
        name = clean_text(data, "name", "Nombre", 80, required=True)
        email = clean_text(data, "email", "Correo", 120, required=True).lower()
        if not EMAIL_PATTERN.match(email):
            raise ValueError("Correo electrónico inválido")
        active = data.get("active", True)
        return {
            "name": name, "email": email,
            "area": clean_text(data, "area", "Área", 80),
            "phone": clean_text(data, "phone", "Teléfono", 40),
            "active": 0 if active in (False, 0, "0", "false") else 1,
        }

    def create_developer(self, data) -> dict:
        record = self._validate_developer(data)
        with self._lock, self._connection() as conn:
            if conn.execute("SELECT 1 FROM developers WHERE email = ?", (record["email"],)).fetchone():
                raise ValueError("Ya existe un programador con ese correo")
            cur = conn.execute("INSERT INTO developers (name, email, area, phone, active, created_at) "
                               "VALUES (?, ?, ?, ?, ?, ?)",
                               (record["name"], record["email"], record["area"], record["phone"],
                                record["active"], now_str()))
        return self.get_developer(cur.lastrowid)

    def update_developer(self, dev_id, data) -> dict:
        current = self.get_developer(dev_id)
        record = self._validate_developer({**current, **(data or {})})
        with self._lock, self._connection() as conn:
            if conn.execute("SELECT 1 FROM developers WHERE email = ? AND id <> ?",
                            (record["email"], dev_id)).fetchone():
                raise ValueError("Ya existe un programador con ese correo")
            conn.execute("UPDATE developers SET name=?, email=?, area=?, phone=?, active=? WHERE id=?",
                         (record["name"], record["email"], record["area"], record["phone"], record["active"],
                          dev_id))
        return self.get_developer(dev_id)

    def delete_developer(self, dev_id) -> None:
        self.get_developer(dev_id)
        with self._lock, self._connection() as conn:
            # Las novedades y aplicaciones quedan sin asignar en lugar de borrarse.
            conn.execute("UPDATE incidents SET developer_id = NULL WHERE developer_id = ?", (dev_id,))
            conn.execute("UPDATE targets SET developer_id = NULL WHERE developer_id = ?", (dev_id,))
            conn.execute("DELETE FROM developers WHERE id = ?", (dev_id,))

    # ------------------------------------------------------------------ aplicaciones
    TARGET_SQL = """
        SELECT t.*, d.name AS developer_name,
               (SELECT s.scan_id FROM scans s WHERE s.target_id = t.id ORDER BY s.id DESC LIMIT 1) AS last_scan_id,
               (SELECT s.status FROM scans s WHERE s.target_id = t.id ORDER BY s.id DESC LIMIT 1) AS last_scan_status,
               (SELECT s.errors + s.network_errors FROM scans s WHERE s.target_id = t.id
                ORDER BY s.id DESC LIMIT 1) AS last_scan_errors,
               (SELECT s.started_at FROM scans s WHERE s.target_id = t.id ORDER BY s.id DESC LIMIT 1) AS last_scan_at
        FROM targets t LEFT JOIN developers d ON d.id = t.developer_id
    """

    def list_targets(self) -> list:
        return self._all(self.TARGET_SQL + " ORDER BY t.name")

    def get_target(self, target_id) -> dict:
        target = self._one(self.TARGET_SQL + " WHERE t.id = ?", (target_id,))
        if target is None:
            raise NotFoundError("Aplicación no encontrada")
        return target

    def _validate_target(self, data):
        dev_id = (data or {}).get("developer_id") or None
        if dev_id is not None:
            self.get_developer(int(dev_id))
        try:
            max_pages = int(data.get("max_pages") or 1)
        except (TypeError, ValueError):
            raise ValueError("Páginas a recorrer debe ser numérico") from None
        if not 1 <= max_pages <= 20:
            raise ValueError("Páginas a recorrer debe estar entre 1 y 20")
        return {
            "name": clean_text(data, "name", "Nombre", 80, required=True),
            "url": clean_url(data.get("url")),
            "environment": clean_choice(data, "environment", "Ambiente", ENVIRONMENTS, "Local"),
            "developer_id": int(dev_id) if dev_id else None,
            "monitor": 1 if data.get("monitor") in (True, 1, "1", "true", "on") else 0,
            "max_pages": max_pages,
            "notes": clean_text(data, "notes", "Notas", 1000),
        }

    def create_target(self, data) -> dict:
        r = self._validate_target(data or {})
        with self._lock, self._connection() as conn:
            cur = conn.execute("INSERT INTO targets (name, url, environment, developer_id, monitor, max_pages, notes, "
                               "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                               (r["name"], r["url"], r["environment"], r["developer_id"], r["monitor"],
                                r["max_pages"], r["notes"], now_str()))
        return self.get_target(cur.lastrowid)

    def update_target(self, target_id, data) -> dict:
        current = self.get_target(target_id)
        r = self._validate_target({**current, **(data or {})})
        with self._lock, self._connection() as conn:
            conn.execute("UPDATE targets SET name=?, url=?, environment=?, developer_id=?, monitor=?, max_pages=?, "
                         "notes=? WHERE id=?",
                         (r["name"], r["url"], r["environment"], r["developer_id"], r["monitor"], r["max_pages"],
                          r["notes"], target_id))
        return self.get_target(target_id)

    def delete_target(self, target_id) -> None:
        self.get_target(target_id)
        with self._lock, self._connection() as conn:
            conn.execute("UPDATE scans SET target_id = NULL WHERE target_id = ?", (target_id,))
            conn.execute("DELETE FROM targets WHERE id = ?", (target_id,))

    def monitored_targets(self) -> list:
        return self._all("SELECT * FROM targets WHERE monitor = 1 ORDER BY id")

    # ------------------------------------------------------------------ análisis de URL
    def create_scan(self, url, target_id, executed_by, trigger) -> dict:
        with self._lock, self._connection() as conn:
            cur = conn.execute('INSERT INTO scans (url, target_id, status, executed_by, "trigger", started_at) '
                               "VALUES (?, ?, 'En curso', ?, ?, ?)", (url, target_id, executed_by, trigger, now_str()))
            scan_id = f"SCAN-{cur.lastrowid + 1000}"
            conn.execute("UPDATE scans SET scan_id = ? WHERE id = ?", (scan_id, cur.lastrowid))
        return self.get_scan(scan_id)

    def finish_scan(self, scan_id, result: dict, issues: list) -> dict:
        errors = sum(1 for i in issues if i["level"] == "error" and i["source"] != "network")
        network = sum(1 for i in issues if i["source"] == "network")
        warnings = sum(1 for i in issues if i["level"] == "warning" and i["source"] != "network")
        status = result.get("status") or ("Con errores" if errors or network else "Sin errores")
        with self._lock, self._connection() as conn:
            conn.execute(
                "UPDATE scans SET status=?, engine=?, http_status=?, load_ms=?, page_title=?, pages_scanned=?, "
                "errors=?, warnings=?, network_errors=?, message=?, has_screenshot=?, finished_at=? WHERE scan_id=?",
                (status, result.get("engine", ""), result.get("http_status"), result.get("load_ms"),
                 (result.get("page_title") or "")[:200], result.get("pages_scanned", 0), errors, warnings, network,
                 result.get("message", ""), 1 if result.get("has_screenshot") else 0, now_str(), scan_id))
            conn.executemany(
                "INSERT INTO scan_issues (scan_id, level, source, message, page_url, resource_url, location, "
                "fingerprint) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(scan_id, i["level"], i["source"], i["message"][:4000], i.get("page_url", ""),
                  i.get("resource_url", "")[:1000], i.get("location", ""),
                  issue_fingerprint(i.get("page_url", ""), i["source"], i["message"])) for i in issues])
        return self.get_scan(scan_id)

    SCAN_SQL = 'SELECT s.*, t.name AS target_name FROM scans s LEFT JOIN targets t ON t.id = s.target_id'

    def list_scans(self, limit=100) -> list:
        return self._all(self.SCAN_SQL + " ORDER BY s.id DESC LIMIT ?", (limit,))

    def get_scan(self, scan_id, with_issues=False) -> dict:
        scan = self._one(self.SCAN_SQL + " WHERE s.scan_id = ?", (scan_id,))
        if scan is None:
            raise NotFoundError("Análisis no encontrado")
        if with_issues:
            scan["issues"] = self._all(
                "SELECT si.*, i.code AS incident_code FROM scan_issues si LEFT JOIN incidents i ON i.id = si.incident_id "
                "WHERE si.scan_id = ? ORDER BY CASE si.level WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, "
                "si.id", (scan_id,))
        return scan

    def get_scan_issues(self, scan_id, issue_ids=None) -> list:
        issues = self.get_scan(scan_id, with_issues=True)["issues"]
        if issue_ids:
            wanted = {int(i) for i in issue_ids}
            issues = [i for i in issues if i["id"] in wanted]
        return issues

    def link_issue(self, issue_id, incident_id) -> None:
        with self._lock, self._connection() as conn:
            conn.execute("UPDATE scan_issues SET incident_id = ? WHERE id = ?", (incident_id, issue_id))

    def delete_scan(self, scan_id) -> None:
        self.get_scan(scan_id)
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM scan_issues WHERE scan_id = ?", (scan_id,))
            conn.execute("DELETE FROM scans WHERE scan_id = ?", (scan_id,))
        path = os.path.join(self.screenshots_dir, f"{scan_id}.png")
        if os.path.isfile(path):
            os.remove(path)

    def mark_stale_scans(self) -> None:
        """Análisis que quedaron 'En curso' por un reinicio del servidor."""
        with self._lock, self._connection() as conn:
            conn.execute("UPDATE scans SET status='Error', message='Interrumpido por reinicio del servidor', "
                         "finished_at=? WHERE status='En curso'", (now_str(),))

    # ------------------------------------------------------------------ novedades
    INCIDENT_SQL = """
        SELECT i.*, d.name AS developer_name, d.email AS developer_email
        FROM incidents i LEFT JOIN developers d ON d.id = i.developer_id
    """

    def list_incidents(self, filters=None) -> list:
        filters = filters or {}
        where, params = [], []
        for key in ("status", "severity", "priority", "source", "environment"):
            if filters.get(key):
                where.append(f"i.{key} = ?")
                params.append(filters[key])
        if filters.get("developer_id"):
            if filters["developer_id"] == "none":
                where.append("i.developer_id IS NULL")
            else:
                where.append("i.developer_id = ?")
                params.append(int(filters["developer_id"]))
        if filters.get("open") in ("1", "true"):
            where.append("i.status IN (" + ", ".join("?" for _ in OPEN_STATUSES) + ")")
            params.extend(OPEN_STATUSES)
        if filters.get("q"):
            where.append("(i.code LIKE ? OR i.title LIKE ? OR i.description LIKE ? OR i.module LIKE ? OR i.url LIKE ?)")
            params.extend([f"%{filters['q']}%"] * 5)
        sql = self.INCIDENT_SQL + (" WHERE " + " AND ".join(where) if where else "")
        sql += (" ORDER BY CASE i.severity WHEN 'Crítica' THEN 0 WHEN 'Alta' THEN 1 WHEN 'Media' THEN 2 ELSE 3 END, "
                "i.id DESC") if filters.get("order") == "severity" else " ORDER BY i.id DESC"
        return self._all(sql, params)

    def get_incident(self, incident_id, with_history=False) -> dict:
        incident = self._one(self.INCIDENT_SQL + " WHERE i.id = ?", (incident_id,))
        if incident is None:
            raise NotFoundError("Novedad no encontrada")
        if with_history:
            incident["history"] = self._all("SELECT * FROM incident_history WHERE incident_id = ? ORDER BY id DESC",
                                            (incident_id,))
        return incident

    def find_open_incident_by_fingerprint(self, fingerprint):
        if not fingerprint:
            return None
        return self._one("SELECT * FROM incidents WHERE fingerprint = ? AND status NOT IN ('Cerrada', 'Verificada') "
                         "ORDER BY id DESC LIMIT 1", (fingerprint,))

    def _validate_incident(self, data):
        dev_id = data.get("developer_id") or None
        if dev_id is not None:
            self.get_developer(int(dev_id))
        due = clean_text(data, "due_date", "Fecha límite", 10)
        if due and not re.match(r"^\d{4}-\d{2}-\d{2}$", due):
            raise ValueError("Fecha límite inválida (AAAA-MM-DD)")
        return {
            "title": clean_text(data, "title", "Título", 200, required=True),
            "description": clean_text(data, "description", "Descripción", 8000),
            "steps": clean_text(data, "steps", "Pasos para reproducir", 4000),
            "expected": clean_text(data, "expected", "Resultado esperado", 2000),
            "actual": clean_text(data, "actual", "Resultado actual", 4000),
            "severity": clean_choice(data, "severity", "Severidad", SEVERITIES, "Media"),
            "priority": clean_choice(data, "priority", "Prioridad", PRIORITIES, "Normal"),
            "status": clean_choice(data, "status", "Estado", INCIDENT_STATUSES, "Nueva"),
            "module": clean_text(data, "module", "Módulo", 80),
            "url": clean_url(data.get("url"), required=False),
            "environment": clean_choice(data, "environment", "Ambiente", ENVIRONMENTS, "QA"),
            "developer_id": int(dev_id) if dev_id else None,
            "due_date": due,
        }

    def create_incident(self, data, reported_by, source="Manual", source_ref="", fingerprint="") -> dict:
        if not isinstance(data, dict):
            raise ValueError("El cuerpo de la petición debe ser JSON")
        r = self._validate_incident(data)
        if r["developer_id"] and r["status"] == "Nueva":
            r["status"] = "Asignada"
        now = now_str()
        with self._lock, self._connection() as conn:
            cur = conn.execute(
                "INSERT INTO incidents (title, description, steps, expected, actual, severity, priority, status, "
                "module, url, environment, developer_id, due_date, source, source_ref, fingerprint, reported_by, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (r["title"], r["description"], r["steps"], r["expected"], r["actual"], r["severity"], r["priority"],
                 r["status"], r["module"], r["url"], r["environment"], r["developer_id"], r["due_date"], source,
                 source_ref, fingerprint, reported_by, now, now))
            incident_id = cur.lastrowid
            conn.execute("UPDATE incidents SET code = ? WHERE id = ?", (f"NOV-{incident_id:04d}", incident_id))
        self.add_history(incident_id, "Creación", f"Novedad registrada (origen: {source}"
                         + (f", ref. {source_ref}" if source_ref else "") + ")", reported_by)
        return self.get_incident(incident_id)

    def update_incident(self, incident_id, data, author) -> dict:
        current = self.get_incident(incident_id)
        r = self._validate_incident({**current, **(data or {})})
        changes = []
        labels = {"status": "Estado", "severity": "Severidad", "priority": "Prioridad", "developer_id": "Asignado a",
                  "title": "Título", "due_date": "Fecha límite"}
        for key, label in labels.items():
            if r[key] != current[key]:
                old, new = current[key], r[key]
                if key == "developer_id":
                    old = current["developer_name"] or "Sin asignar"
                    new = self.get_developer(new)["name"] if new else "Sin asignar"
                changes.append(f"{label}: {old or '—'} → {new or '—'}")
        if r["developer_id"] and not current["developer_id"] and r["status"] == "Nueva":
            r["status"] = "Asignada"
        with self._lock, self._connection() as conn:
            conn.execute(
                "UPDATE incidents SET title=?, description=?, steps=?, expected=?, actual=?, severity=?, priority=?, "
                "status=?, module=?, url=?, environment=?, developer_id=?, due_date=?, updated_at=? WHERE id=?",
                (r["title"], r["description"], r["steps"], r["expected"], r["actual"], r["severity"], r["priority"],
                 r["status"], r["module"], r["url"], r["environment"], r["developer_id"], r["due_date"], now_str(),
                 incident_id))
        if changes:
            self.add_history(incident_id, "Cambio", "; ".join(changes), author)
        elif any(r[k] != current[k] for k in r):
            self.add_history(incident_id, "Cambio", "Se editaron los detalles de la novedad", author)
        return self.get_incident(incident_id)

    def register_occurrence(self, incident_id, detail, author) -> dict:
        incident = self.get_incident(incident_id)
        reopen = incident["status"] == "Resuelta"
        with self._lock, self._connection() as conn:
            conn.execute("UPDATE incidents SET occurrences = occurrences + 1, updated_at = ?"
                         + (", status = 'Reabierta'" if reopen else "") + " WHERE id = ?", (now_str(), incident_id))
        self.add_history(incident_id, "Reaparición",
                         detail + (" — se reabre porque estaba marcada como resuelta" if reopen else ""), author)
        return self.get_incident(incident_id)

    def delete_incident(self, incident_id) -> None:
        self.get_incident(incident_id)
        with self._lock, self._connection() as conn:
            conn.execute("UPDATE scan_issues SET incident_id = NULL WHERE incident_id = ?", (incident_id,))
            conn.execute("DELETE FROM incident_history WHERE incident_id = ?", (incident_id,))
            conn.execute("DELETE FROM incidents WHERE id = ?", (incident_id,))

    def add_history(self, incident_id, kind, detail, author) -> dict:
        with self._lock, self._connection() as conn:
            cur = conn.execute("INSERT INTO incident_history (incident_id, kind, detail, author, created_at) "
                               "VALUES (?, ?, ?, ?, ?)", (incident_id, kind, detail, author, now_str()))
        return self._one("SELECT * FROM incident_history WHERE id = ?", (cur.lastrowid,))

    def mark_notified(self, incident_id) -> None:
        with self._lock, self._connection() as conn:
            conn.execute("UPDATE incidents SET notified_at = ? WHERE id = ?", (now_str(), incident_id))

    def incident_summary(self) -> dict:
        rows = self._all("SELECT status, severity, COUNT(*) AS n FROM incidents GROUP BY status, severity")
        by_status = {s: 0 for s in INCIDENT_STATUSES}
        by_severity_open = {s: 0 for s in SEVERITIES}
        for r in rows:
            by_status[r["status"]] = by_status.get(r["status"], 0) + r["n"]
            if r["status"] in OPEN_STATUSES:
                by_severity_open[r["severity"]] = by_severity_open.get(r["severity"], 0) + r["n"]
        open_total = sum(by_status[s] for s in OPEN_STATUSES)
        unassigned = self._one("SELECT COUNT(*) AS n FROM incidents WHERE developer_id IS NULL AND status IN ("
                               + ", ".join("?" for _ in OPEN_STATUSES) + ")", OPEN_STATUSES)["n"]
        return {
            "total": sum(by_status.values()),
            "open": open_total,
            "unassigned": unassigned,
            "by_status": by_status,
            "by_severity_open": by_severity_open,
            "recent": self.list_incidents({"open": "1", "order": "severity"})[:6],
        }

    def scan_summary(self) -> dict:
        last = self._all(self.SCAN_SQL + " ORDER BY s.id DESC LIMIT 5")
        totals = self._one("SELECT COUNT(*) AS n, COALESCE(SUM(errors + network_errors), 0) AS issues FROM scans")
        return {"total": totals["n"], "issues": totals["issues"], "recent": last}


store = QAStore(os.environ.get("QA_DB_PATH", DEFAULT_DB_PATH))
