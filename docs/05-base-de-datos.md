# 5. Base de datos

Archivo: `C:\Users\Pc\Downloads\qa-center\backend\data\qa_reports.db` (SQLite). Las tablas se crean solas al arrancar (`CREATE TABLE IF NOT EXISTS`)
desde tres archivos: `reports_engine.py`, `qa_store.py` y `testdocs.py`.

Para mirar la base por dentro puedes usar [DB Browser for SQLite](https://sqlitebrowser.org/) o desde Python:

```python
import sqlite3
conn = sqlite3.connect("backend/data/qa_reports.db")
for row in conn.execute("SELECT code, title, status FROM incidents"):
    print(row)
```

## 5.1 Diagrama de relaciones

```
developers ──┐ (developer_id)
             ├──< targets ──< scans ──< scan_issues >── incidents
             └──< incidents ──< incident_history
                     ▲
                     │ (incident_id)
test_plans ──< test_specs ──< spec_executions
     │             │  └──< spec_evidence
     │             └──< spec_requirements >── requirements
     └──< requirements

test_runs ──< test_cases          settings (clave → valor)

   A ──< B  significa "un A tiene muchos B".
```

## 5.2 Tablas

### Pruebas ejecutadas (`reports_engine.py`)

**test_runs** — una ejecución de una suite (automática, registrada a mano o importada).

| Columna | Significado |
|---|---|
| `run_id` | Código `RUN-1001` |
| `batch_id` | Lote de pruebas automáticas (vacío si es manual o importada) |
| `suite`, `tool`, `module`, `environment`, `url` | Qué se probó, con qué herramienta y dónde |
| `total`, `passed`, `failed`, `skipped`, `pass_rate` | Números (passed y pass_rate se calculan) |
| `status` | `Passed` si no hay fallidas, si no `Failed` |
| `trigger` | Origen: Programada, Manual, Registro manual, Importación |
| `notes`, `evidence_url` | Observaciones y enlace a evidencia |
| `executed_by`, `executed_at`, `updated_at` | Quién y cuándo |

**test_cases** — cada caso de una ejecución automática o importada (nombre, estado, tiempo, detalle del error).

### Seguimiento (`qa_store.py`)

**developers** — `name`, `email` (único), `area`, `phone`, `active`.

**targets** — aplicaciones: `name`, `url`, `environment`, `developer_id` (responsable), `monitor` (1 = automático),
`max_pages`.

**scans** — un análisis de URL: `scan_id` (`SCAN-1001`), `url`, `status` (En curso, Sin errores, Con errores, Error),
`engine`, `http_status`, `load_ms`, contadores `errors` / `network_errors` / `warnings`, `has_screenshot`, `trigger`.

**scan_issues** — cada error encontrado: `level` (error/warning), `source` (console, javascript, network, navegador),
`message`, `page_url`, `resource_url`, `location`, `fingerprint` (huella) e `incident_id` (novedad creada).

**incidents** — novedades/defectos: `code` (`NOV-0001`), `title`, `description`, `steps`, `expected`, `actual`,
`severity`, `priority`, `status`, `module`, `url`, `environment`, `developer_id`, `source` y `source_ref` (de dónde
vino: `SCAN-1001`, `RUN-1005`, `CP-0002`), `fingerprint`, `occurrences` (veces detectada), `due_date`,
`notified_at`.

**incident_history** — `kind` (Creación, Cambio, Comentario, Notificación, Reaparición, Error de envío), `detail`,
`author`, `created_at`.

**settings** — configuración como pares `key` / `value`.

### Documentación QA (`testdocs.py`)

**test_plans** — `code` (`PLN-001`), `name`, `version`, `status`, `responsible`, fechas y las secciones de texto
(`objective`, `scope_in`, `scope_out`, `features`, `approach`, `acceptance_criteria`, `resources`, `schedule`,
`risks`).

**requirements** — `code` (`HU-01` o automático `REQ-001`, único), `title`, `kind`, `description`, `priority`,
`module`, `plan_id`.

**test_specs** — casos de prueba: `code` (`CP-0001`), `plan_id`, `title`, `description`, `module`, `type`,
`priority`, `tool`, `preconditions`, `input_data`, `steps`, `expected`, `actual`, `status`, `executed_by`,
`executed_at`, `evidence_notes`, `incident_id` (defecto asociado).

**spec_requirements** — tabla intermedia `spec_id` + `requirement_id`: un caso cubre varios requisitos y un requisito
tiene varios casos (**muchos a muchos**). Es la base de la matriz de trazabilidad.

**spec_executions** — historial de cada ejecución de un caso.

**spec_evidence** — archivos adjuntos: `filename` (nombre original), `stored_name` (nombre aleatorio en disco),
`mimetype`, `size`.

## 5.3 Consultas útiles para practicar SQL

```sql
-- Novedades abiertas por programador
SELECT d.name, COUNT(*) AS abiertas
FROM incidents i JOIN developers d ON d.id = i.developer_id
WHERE i.status IN ('Nueva', 'Asignada', 'En progreso', 'Reabierta')
GROUP BY d.name ORDER BY abiertas DESC;

-- Errores que más se repiten
SELECT code, title, occurrences FROM incidents ORDER BY occurrences DESC LIMIT 10;

-- Requisitos sin ningún caso de prueba
SELECT r.code, r.title FROM requirements r
WHERE r.id NOT IN (SELECT requirement_id FROM spec_requirements);

-- Pass rate por herramienta
SELECT tool, SUM(passed) * 100.0 / SUM(total) AS pass_rate FROM test_runs GROUP BY tool;
```
