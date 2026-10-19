"""Documentación QA: planes de prueba, requisitos / historias de usuario, casos de prueba con evidencias y
matriz de trazabilidad (RTM). Comparte la base SQLite con el resto de QA Center."""
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager

from qa_store import NotFoundError, PRIORITIES, clean_choice, clean_text, clean_url
from reports_engine import DEFAULT_DB_PATH, ENVIRONMENTS, TOOLS, now_str, parse_datetime

PLAN_STATUSES = ["Borrador", "En revisión", "Aprobado", "En ejecución", "Cerrado"]
CASE_STATUSES = ["No ejecutado", "Aprobado", "Fallido", "Bloqueado", "Omitido"]
CASE_TYPES = ["Funcional", "Regresión", "Integración", "API", "Interfaz (UI)", "Seguridad", "Rendimiento",
              "Usabilidad", "Aceptación"]
REQUIREMENT_KINDS = ["Requerimiento", "Historia de usuario", "Regla de negocio", "Requisito no funcional"]
EVIDENCE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".txt", ".log", ".json", ".har", ".csv",
                       ".xml", ".html", ".mp4", ".webm", ".zip"}
MAX_EVIDENCE_BYTES = 10 * 1024 * 1024

SCHEMA = """
CREATE TABLE IF NOT EXISTS test_plans (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    code                TEXT UNIQUE,
    name                TEXT NOT NULL,
    version             TEXT NOT NULL DEFAULT '1.0',
    status              TEXT NOT NULL,
    responsible         TEXT NOT NULL DEFAULT '',
    environment         TEXT NOT NULL DEFAULT 'QA',
    start_date          TEXT NOT NULL DEFAULT '',
    end_date            TEXT NOT NULL DEFAULT '',
    objective           TEXT NOT NULL DEFAULT '',
    scope_in            TEXT NOT NULL DEFAULT '',
    scope_out           TEXT NOT NULL DEFAULT '',
    features            TEXT NOT NULL DEFAULT '',
    approach            TEXT NOT NULL DEFAULT '',
    acceptance_criteria TEXT NOT NULL DEFAULT '',
    resources           TEXT NOT NULL DEFAULT '',
    schedule            TEXT NOT NULL DEFAULT '',
    risks               TEXT NOT NULL DEFAULT '',
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS requirements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    code         TEXT UNIQUE NOT NULL,
    title        TEXT NOT NULL,
    kind         TEXT NOT NULL,
    description  TEXT NOT NULL DEFAULT '',
    priority     TEXT NOT NULL,
    module       TEXT NOT NULL DEFAULT '',
    plan_id      INTEGER,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS test_specs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT UNIQUE,
    plan_id         INTEGER,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    module          TEXT NOT NULL DEFAULT '',
    type            TEXT NOT NULL,
    priority        TEXT NOT NULL,
    tool            TEXT NOT NULL DEFAULT 'Manual',
    preconditions   TEXT NOT NULL DEFAULT '',
    input_data      TEXT NOT NULL DEFAULT '',
    steps           TEXT NOT NULL DEFAULT '',
    expected        TEXT NOT NULL DEFAULT '',
    actual          TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL,
    environment     TEXT NOT NULL DEFAULT 'QA',
    url             TEXT NOT NULL DEFAULT '',
    executed_by     TEXT NOT NULL DEFAULT '',
    executed_at     TEXT NOT NULL DEFAULT '',
    evidence_notes  TEXT NOT NULL DEFAULT '',
    incident_id     INTEGER,
    created_by      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spec_requirements (
    spec_id         INTEGER NOT NULL,
    requirement_id  INTEGER NOT NULL,
    PRIMARY KEY (spec_id, requirement_id)
);
CREATE TABLE IF NOT EXISTS spec_executions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id      INTEGER NOT NULL,
    status       TEXT NOT NULL,
    actual       TEXT NOT NULL DEFAULT '',
    executed_by  TEXT NOT NULL,
    executed_at  TEXT NOT NULL,
    incident_id  INTEGER
);
CREATE TABLE IF NOT EXISTS spec_evidence (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id      INTEGER NOT NULL,
    filename     TEXT NOT NULL,
    stored_name  TEXT NOT NULL,
    mimetype     TEXT NOT NULL,
    size         INTEGER NOT NULL,
    uploaded_by  TEXT NOT NULL,
    created_at   TEXT NOT NULL
);
"""

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _date(data, key, label):
    value = clean_text(data, key, label, 10)
    if value and not DATE_RE.match(value):
        raise ValueError(f"{label} inválida (AAAA-MM-DD)")
    return value


class TestDocsStore:
    __test__ = False

    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = threading.RLock()
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        with self._connection() as conn:
            conn.executescript(SCHEMA)

    @property
    def evidence_dir(self):
        path = os.path.join(os.path.dirname(os.path.abspath(self.db_path)), "evidencias")
        os.makedirs(path, exist_ok=True)
        return path

    @contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
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

    def _insert(self, table, record, code_prefix=None, code_width=4):
        columns = list(record)
        with self._lock, self._connection() as conn:
            cur = conn.execute(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
                               [record[c] for c in columns])
            new_id = cur.lastrowid
            if code_prefix:
                conn.execute(f"UPDATE {table} SET code = ? WHERE id = ?", (f"{code_prefix}-{new_id:0{code_width}d}", new_id))
        return new_id

    def _update(self, table, row_id, record):
        columns = list(record)
        with self._lock, self._connection() as conn:
            conn.execute(f"UPDATE {table} SET {', '.join(c + ' = ?' for c in columns)} WHERE id = ?",
                         [record[c] for c in columns] + [row_id])

    # ------------------------------------------------------------------ planes
    def _validate_plan(self, data):
        if not isinstance(data, dict):
            raise ValueError("El cuerpo de la petición debe ser JSON")
        record = {
            "name": clean_text(data, "name", "Nombre", 150, required=True),
            "version": clean_text(data, "version", "Versión", 20) or "1.0",
            "status": clean_choice(data, "status", "Estado", PLAN_STATUSES, "Borrador"),
            "responsible": clean_text(data, "responsible", "Responsable", 120),
            "environment": clean_choice(data, "environment", "Ambiente", ENVIRONMENTS, "QA"),
            "start_date": _date(data, "start_date", "Fecha de inicio"),
            "end_date": _date(data, "end_date", "Fecha de fin"),
        }
        for key, label in (("objective", "Objetivo"), ("scope_in", "Alcance"), ("scope_out", "Fuera de alcance"),
                           ("features", "Funciones a evaluar"), ("approach", "Estrategia"),
                           ("acceptance_criteria", "Criterios de aceptación"), ("resources", "Recursos"),
                           ("schedule", "Cronograma"), ("risks", "Riesgos")):
            record[key] = clean_text(data, key, label, 8000)
        if record["start_date"] and record["end_date"] and record["end_date"] < record["start_date"]:
            raise ValueError("La fecha de fin no puede ser anterior a la de inicio")
        return record

    def list_plans(self):
        plans = self._all("SELECT * FROM test_plans ORDER BY id DESC")
        for plan in plans:
            plan["summary"] = self.plan_summary(plan["id"])
        return plans

    def get_plan(self, plan_id):
        plan = self._one("SELECT * FROM test_plans WHERE id = ?", (plan_id,))
        if plan is None:
            raise NotFoundError("Plan de pruebas no encontrado")
        plan["summary"] = self.plan_summary(plan_id)
        return plan

    def create_plan(self, data):
        record = self._validate_plan(data)
        record["created_at"] = record["updated_at"] = now_str()
        return self.get_plan(self._insert("test_plans", record, "PLN", 3))

    def update_plan(self, plan_id, data):
        current = self.get_plan(plan_id)
        record = self._validate_plan({**current, **(data or {})})
        record["updated_at"] = now_str()
        self._update("test_plans", plan_id, record)
        return self.get_plan(plan_id)

    def delete_plan(self, plan_id):
        self.get_plan(plan_id)
        with self._lock, self._connection() as conn:
            # Los casos y requisitos se conservan sin plan.
            conn.execute("UPDATE test_specs SET plan_id = NULL WHERE plan_id = ?", (plan_id,))
            conn.execute("UPDATE requirements SET plan_id = NULL WHERE plan_id = ?", (plan_id,))
            conn.execute("DELETE FROM test_plans WHERE id = ?", (plan_id,))

    def plan_summary(self, plan_id=None):
        where, params = ("WHERE plan_id = ?", (plan_id,)) if plan_id else ("", ())
        rows = self._all(f"SELECT status, COUNT(*) AS n FROM test_specs {where} GROUP BY status", params)
        by_status = {s: 0 for s in CASE_STATUSES}
        for r in rows:
            by_status[r["status"]] = r["n"]
        total = sum(by_status.values())
        executed = total - by_status["No ejecutado"]
        rtm = self.traceability(plan_id)
        return {
            "cases": total, "executed": executed, "by_status": by_status,
            "execution_rate": round(executed / total * 100, 1) if total else 0.0,
            "pass_rate": round(by_status["Aprobado"] / executed * 100, 1) if executed else 0.0,
            "requirements": rtm["totals"]["requirements"], "covered": rtm["totals"]["covered"],
            "coverage": rtm["totals"]["coverage"],
        }

    # ------------------------------------------------------------------ requisitos
    def _validate_requirement(self, data, current_id=None):
        if not isinstance(data, dict):
            raise ValueError("El cuerpo de la petición debe ser JSON")
        plan_id = data.get("plan_id") or None
        if plan_id:
            self.get_plan(int(plan_id))
        code = clean_text(data, "code", "Código", 30).upper()
        if code:
            if not re.match(r"^[A-Z0-9][A-Z0-9._-]*$", code):
                raise ValueError("El código solo admite letras, números, punto, guion y guion bajo (ej.: HU-01)")
            clash = self._one("SELECT id FROM requirements WHERE code = ? AND id <> ?", (code, current_id or 0))
            if clash:
                raise ValueError(f"Ya existe un requisito con el código {code}")
        return {
            "code": code,
            "title": clean_text(data, "title", "Título", 200, required=True),
            "kind": clean_choice(data, "kind", "Tipo", REQUIREMENT_KINDS, "Requerimiento"),
            "description": clean_text(data, "description", "Descripción", 4000),
            "priority": clean_choice(data, "priority", "Prioridad", PRIORITIES, "Normal"),
            "module": clean_text(data, "module", "Módulo", 80),
            "plan_id": int(plan_id) if plan_id else None,
        }

    def list_requirements(self, plan_id=None):
        sql = ("SELECT r.*, p.code AS plan_code, (SELECT COUNT(*) FROM spec_requirements sr WHERE sr.requirement_id = r.id)"
               " AS cases FROM requirements r LEFT JOIN test_plans p ON p.id = r.plan_id")
        if plan_id:
            return self._all(sql + " WHERE r.plan_id = ? ORDER BY r.code", (plan_id,))
        return self._all(sql + " ORDER BY r.code")

    def get_requirement(self, req_id):
        req = self._one("SELECT * FROM requirements WHERE id = ?", (req_id,))
        if req is None:
            raise NotFoundError("Requisito no encontrado")
        return req

    def create_requirement(self, data):
        record = self._validate_requirement(data)
        auto_code = not record["code"]
        if auto_code:
            record["code"] = f"TMP-{uuid.uuid4().hex[:8]}"
        record["created_at"] = record["updated_at"] = now_str()
        req_id = self._insert("requirements", record)
        if auto_code:
            self._update("requirements", req_id, {"code": f"REQ-{req_id:03d}"})
        return self.get_requirement(req_id)

    def update_requirement(self, req_id, data):
        current = self.get_requirement(req_id)
        record = self._validate_requirement({**current, **(data or {})}, current_id=req_id)
        record["code"] = record["code"] or current["code"]
        record["updated_at"] = now_str()
        self._update("requirements", req_id, record)
        return self.get_requirement(req_id)

    def delete_requirement(self, req_id):
        self.get_requirement(req_id)
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM spec_requirements WHERE requirement_id = ?", (req_id,))
            conn.execute("DELETE FROM requirements WHERE id = ?", (req_id,))

    # ------------------------------------------------------------------ casos de prueba
    SPEC_SQL = """
        SELECT s.*, p.code AS plan_code, p.name AS plan_name, i.code AS incident_code, i.status AS incident_status,
               (SELECT COUNT(*) FROM spec_evidence e WHERE e.spec_id = s.id) AS evidence_count
        FROM test_specs s LEFT JOIN test_plans p ON p.id = s.plan_id LEFT JOIN incidents i ON i.id = s.incident_id
    """

    def _attach_requirements(self, specs):
        if not specs:
            return specs
        ids = [s["id"] for s in specs]
        links = self._all("SELECT sr.spec_id, r.id, r.code, r.title FROM spec_requirements sr "
                          "JOIN requirements r ON r.id = sr.requirement_id WHERE sr.spec_id IN ("
                          + ", ".join("?" for _ in ids) + ") ORDER BY r.code", ids)
        for spec in specs:
            spec["requirements"] = [{"id": l["id"], "code": l["code"], "title": l["title"]}
                                    for l in links if l["spec_id"] == spec["id"]]
        return specs

    def list_specs(self, filters=None):
        filters = filters or {}
        where, params = [], []
        for key in ("plan_id", "status", "type", "priority", "module"):
            if filters.get(key):
                where.append(f"s.{key} = ?")
                params.append(filters[key])
        if filters.get("requirement_id"):
            where.append("s.id IN (SELECT spec_id FROM spec_requirements WHERE requirement_id = ?)")
            params.append(int(filters["requirement_id"]))
        if filters.get("q"):
            where.append("(s.code LIKE ? OR s.title LIKE ? OR s.module LIKE ? OR s.description LIKE ?)")
            params.extend([f"%{filters['q']}%"] * 4)
        sql = self.SPEC_SQL + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY s.id"
        return self._attach_requirements(self._all(sql, params))

    def get_spec(self, spec_id, full=False):
        spec = self._one(self.SPEC_SQL + " WHERE s.id = ?", (spec_id,))
        if spec is None:
            raise NotFoundError("Caso de prueba no encontrado")
        self._attach_requirements([spec])
        if full:
            spec["evidence"] = self._all("SELECT * FROM spec_evidence WHERE spec_id = ? ORDER BY id", (spec_id,))
            spec["executions"] = self._all(
                "SELECT x.*, i.code AS incident_code FROM spec_executions x LEFT JOIN incidents i ON i.id = x.incident_id "
                "WHERE x.spec_id = ? ORDER BY x.id DESC", (spec_id,))
        return spec

    def _validate_spec(self, data):
        if not isinstance(data, dict):
            raise ValueError("El cuerpo de la petición debe ser JSON")
        plan_id = data.get("plan_id") or None
        if plan_id:
            self.get_plan(int(plan_id))
        record = {
            "plan_id": int(plan_id) if plan_id else None,
            "title": clean_text(data, "title", "Título / descripción corta", 200, required=True),
            "description": clean_text(data, "description", "Propósito", 4000),
            "module": clean_text(data, "module", "Módulo", 80),
            "type": clean_choice(data, "type", "Tipo", CASE_TYPES, "Funcional"),
            "priority": clean_choice(data, "priority", "Prioridad", PRIORITIES, "Normal"),
            "tool": clean_choice(data, "tool", "Herramienta", TOOLS, "Manual"),
            "preconditions": clean_text(data, "preconditions", "Precondiciones", 4000),
            "input_data": clean_text(data, "input_data", "Datos de entrada", 4000),
            "steps": clean_text(data, "steps", "Pasos", 8000),
            "expected": clean_text(data, "expected", "Resultado esperado", 4000),
            "actual": clean_text(data, "actual", "Resultado obtenido", 4000),
            "status": clean_choice(data, "status", "Estado", CASE_STATUSES, "No ejecutado"),
            "environment": clean_choice(data, "environment", "Ambiente", ENVIRONMENTS, "QA"),
            "url": clean_url(data.get("url"), required=False),
            "evidence_notes": clean_text(data, "evidence_notes", "Evidencias / logs", 8000),
        }
        req_ids = data.get("requirement_ids")
        if req_ids is not None:
            if not isinstance(req_ids, list):
                raise ValueError("requirement_ids debe ser una lista")
            req_ids = sorted({int(r) for r in req_ids})
            for rid in req_ids:
                self.get_requirement(rid)
        return record, req_ids

    def _set_requirements(self, spec_id, req_ids):
        if req_ids is None:
            return
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM spec_requirements WHERE spec_id = ?", (spec_id,))
            conn.executemany("INSERT INTO spec_requirements (spec_id, requirement_id) VALUES (?, ?)",
                             [(spec_id, r) for r in req_ids])

    def create_spec(self, data, author):
        record, req_ids = self._validate_spec(data)
        record.update(created_by=author, created_at=now_str(), updated_at=now_str())
        spec_id = self._insert("test_specs", record, "CP", 4)
        self._set_requirements(spec_id, req_ids)
        return self.get_spec(spec_id)

    def update_spec(self, spec_id, data):
        current = self.get_spec(spec_id)
        merged = {**current, **(data or {})}
        if "requirement_ids" not in (data or {}):
            merged["requirement_ids"] = None
        record, req_ids = self._validate_spec(merged)
        record["updated_at"] = now_str()
        self._update("test_specs", spec_id, record)
        self._set_requirements(spec_id, req_ids)
        return self.get_spec(spec_id)

    def duplicate_spec(self, spec_id, author):
        spec = self.get_spec(spec_id)
        data = {k: spec[k] for k in ("plan_id", "description", "module", "type", "priority", "tool", "preconditions",
                                     "input_data", "steps", "expected", "environment", "url")}
        data.update(title=f"{spec['title']} (copia)"[:200], requirement_ids=[r["id"] for r in spec["requirements"]])
        return self.create_spec(data, author)

    def record_execution(self, spec_id, data, author, incident_id=None):
        """Registra el resultado de una ejecución del caso (Aprobado, Fallido, Bloqueado u Omitido)."""
        self.get_spec(spec_id)
        status = clean_choice(data, "status", "Resultado", CASE_STATUSES[1:], "Aprobado")
        actual = clean_text(data, "actual", "Resultado obtenido", 4000)
        executed_at = parse_datetime(data.get("executed_at"))
        update = {"status": status, "actual": actual, "executed_by": author, "executed_at": executed_at,
                  "updated_at": now_str()}
        notes = clean_text(data, "evidence_notes", "Evidencias / logs", 8000)
        if notes:
            update["evidence_notes"] = notes
        if incident_id:
            update["incident_id"] = incident_id
        self._update("test_specs", spec_id, update)
        self._insert("spec_executions", {"spec_id": spec_id, "status": status, "actual": actual,
                                         "executed_by": author, "executed_at": executed_at,
                                         "incident_id": incident_id})
        return self.get_spec(spec_id, full=True)

    def link_incident(self, spec_id, incident_id):
        self._update("test_specs", spec_id, {"incident_id": incident_id})

    def delete_spec(self, spec_id):
        self.get_spec(spec_id)
        for ev in self._all("SELECT * FROM spec_evidence WHERE spec_id = ?", (spec_id,)):
            self._remove_file(ev["stored_name"])
        with self._lock, self._connection() as conn:
            for table, column in (("spec_requirements", "spec_id"), ("spec_executions", "spec_id"),
                                  ("spec_evidence", "spec_id"), ("test_specs", "id")):
                conn.execute(f"DELETE FROM {table} WHERE {column} = ?", (spec_id,))

    # ------------------------------------------------------------------ evidencias
    def add_evidence(self, spec_id, filename, content, mimetype, author):
        self.get_spec(spec_id)
        name = os.path.basename(filename or "").strip() or "evidencia"
        ext = os.path.splitext(name)[1].lower()
        if ext not in EVIDENCE_EXTENSIONS:
            raise ValueError("Tipo de archivo no permitido. Use imágenes, PDF, video, logs (txt, log, json, har, xml, "
                             "csv, html) o zip")
        if not content:
            raise ValueError("El archivo está vacío")
        if len(content) > MAX_EVIDENCE_BYTES:
            raise ValueError("La evidencia supera los 10 MB")
        stored = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(self.evidence_dir, stored), "wb") as fh:
            fh.write(content)
        ev_id = self._insert("spec_evidence", {"spec_id": spec_id, "filename": name[:200], "stored_name": stored,
                                               "mimetype": mimetype or "application/octet-stream",
                                               "size": len(content), "uploaded_by": author, "created_at": now_str()})
        return self.get_evidence(ev_id)

    def get_evidence(self, ev_id):
        ev = self._one("SELECT * FROM spec_evidence WHERE id = ?", (ev_id,))
        if ev is None:
            raise NotFoundError("Evidencia no encontrada")
        ev["path"] = os.path.join(self.evidence_dir, ev["stored_name"])
        return ev

    def delete_evidence(self, ev_id):
        ev = self.get_evidence(ev_id)
        self._remove_file(ev["stored_name"])
        with self._lock, self._connection() as conn:
            conn.execute("DELETE FROM spec_evidence WHERE id = ?", (ev_id,))

    def _remove_file(self, stored_name):
        path = os.path.join(self.evidence_dir, stored_name)
        if os.path.isfile(path):
            os.remove(path)

    # ------------------------------------------------------------------ trazabilidad
    def traceability(self, plan_id=None):
        """Matriz requisito → casos. Estado de cobertura por requisito:
        Sin cobertura, Pendiente (casos sin ejecutar), Con fallas, Bloqueado, Validado."""
        requirements = self.list_requirements(plan_id)
        if plan_id:
            spec_filter = " AND (s.plan_id = ? OR s.plan_id IS NULL)"
            params = (plan_id,)
        else:
            spec_filter, params = "", ()
        links = self._all(
            "SELECT sr.requirement_id, s.id, s.code, s.title, s.status, s.incident_id, i.code AS incident_code, "
            "i.status AS incident_status FROM spec_requirements sr JOIN test_specs s ON s.id = sr.spec_id "
            "LEFT JOIN incidents i ON i.id = s.incident_id WHERE 1 = 1" + spec_filter + " ORDER BY s.id", params)
        rows = []
        for req in requirements:
            cases = [l for l in links if l["requirement_id"] == req["id"]]
            statuses = {c["status"] for c in cases}
            if not cases:
                coverage = "Sin cobertura"
            elif "Fallido" in statuses:
                coverage = "Con fallas"
            elif "Bloqueado" in statuses:
                coverage = "Bloqueado"
            elif statuses <= {"Aprobado", "Omitido"} and "Aprobado" in statuses:
                coverage = "Validado"
            else:
                coverage = "Pendiente"
            rows.append({**req, "cases": [{k: c[k] for k in ("id", "code", "title", "status", "incident_code",
                                                              "incident_status")} for c in cases],
                         "coverage": coverage,
                         "defects": sorted({c["incident_code"] for c in cases if c["incident_code"]})})
        orphan_where = "WHERE s.id NOT IN (SELECT spec_id FROM spec_requirements)"
        orphan_params = ()
        if plan_id:
            orphan_where += " AND s.plan_id = ?"
            orphan_params = (plan_id,)
        orphans = self._all(f"SELECT s.id, s.code, s.title, s.status FROM test_specs s {orphan_where} ORDER BY s.id",
                            orphan_params)
        covered = sum(1 for r in rows if r["coverage"] != "Sin cobertura")
        counts = {}
        for r in rows:
            counts[r["coverage"]] = counts.get(r["coverage"], 0) + 1
        return {
            "rows": rows, "orphan_cases": orphans,
            "totals": {"requirements": len(rows), "covered": covered, "by_coverage": counts,
                       "coverage": round(covered / len(rows) * 100, 1) if rows else 0.0,
                       "validated": counts.get("Validado", 0)},
        }


docs = TestDocsStore(os.environ.get("QA_DB_PATH", DEFAULT_DB_PATH))
