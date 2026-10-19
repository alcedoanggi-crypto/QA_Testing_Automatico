"""Genera los reportes que se muestran en el README:

  docs/reportes/pruebas/      resultado de las pruebas automatizadas (JUnit XML, resumen .md e imagen .png)
  docs/reportes/ejemplos/     reportes PDF y Excel de ejemplo generados por QA Center con datos de demostración
  docs/reportes/vistas/       imagen de la primera página de cada PDF
  docs/capturas/              capturas de las pantallas principales

Usa bases de datos temporales; no toca backend/data.

Requisitos extra (solo para este script):  pip install pypdfium2
Ejecutar desde la raíz del proyecto:          python docs/reportes/generar_reportes.py
"""
import datetime as dt
import html
import http.server
import io
import os
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
TESTS_DIR = os.path.join(HERE, "pruebas")
EXAMPLES_DIR = os.path.join(HERE, "ejemplos")
PREVIEWS_DIR = os.path.join(HERE, "vistas")
SCREENS_DIR = os.path.join(ROOT, "docs", "capturas")
for folder in (TESTS_DIR, EXAMPLES_DIR, PREVIEWS_DIR, SCREENS_DIR):
    os.makedirs(folder, exist_ok=True)

TEST_FILES = {
    "test_console_logs.py": "Consola y logs",
    "test_system_runner.py": "Autopruebas y programador",
    "test_qa_center.py": "API: análisis, resultados, novedades, reportes",
    "test_testdocs.py": "API: plan, casos, evidencias, trazabilidad, defectos",
    "test_selenium_ui.py": "E2E con Selenium (navegador real)",
}


# ============================================================================= 1. pruebas automatizadas
def run_tests():
    junit = os.path.join(TESTS_DIR, "junit.xml")
    started = time.time()
    subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q", f"--junitxml={junit}", "-p", "no:cacheprovider"],
                   cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elapsed = time.time() - started

    root = ET.parse(junit).getroot()
    cases = []
    for tc in root.iter("testcase"):
        module = tc.get("classname", "").split(".")
        file_name = next((f"{m}.py" for m in module if m.startswith("test_")), "otros")
        status = "Fallida" if tc.find("failure") is not None or tc.find("error") is not None else (
            "Omitida" if tc.find("skipped") is not None else "Exitosa")
        cases.append({"file": file_name, "name": tc.get("name"), "time": float(tc.get("time") or 0), "status": status})

    by_file = []
    for file_name, label in TEST_FILES.items():
        group = [c for c in cases if c["file"] == file_name]
        by_file.append({"file": file_name, "label": label, "total": len(group),
                        "passed": sum(c["status"] == "Exitosa" for c in group),
                        "failed": sum(c["status"] == "Fallida" for c in group),
                        "time": sum(c["time"] for c in group)})
    summary = {"date": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "total": len(cases),
               "passed": sum(c["status"] == "Exitosa" for c in cases),
               "failed": sum(c["status"] == "Fallida" for c in cases), "elapsed": elapsed}
    write_tests_markdown(summary, by_file, cases)
    write_tests_html(summary, by_file, cases)
    return summary


def write_tests_markdown(summary, by_file, cases):
    lines = [
        "# Resultado de las pruebas automatizadas", "",
        f"Fecha: **{summary['date']}** · Total: **{summary['total']}** · Exitosas: **{summary['passed']}** · "
        f"Fallidas: **{summary['failed']}** · Duración: **{summary['elapsed']:.0f} s**", "",
        "![Resultado de las pruebas](resultado-pruebas.png)", "",
        "| Archivo | Qué prueba | Pruebas | Exitosas | Fallidas | Tiempo |", "|---|---|---|---|---|---|",
    ]
    for f in by_file:
        lines.append(f"| `{f['file']}` | {f['label']} | {f['total']} | {f['passed']} | {f['failed']} | {f['time']:.1f} s |")
    for f in by_file:
        lines += ["", f"## {f['label']} (`{f['file']}`)", "", "| Prueba | Resultado | Tiempo |", "|---|---|---|"]
        for c in (c for c in cases if c["file"] == f["file"]):
            icon = "✅" if c["status"] == "Exitosa" else "❌"
            lines.append(f"| `{c['name']}` | {icon} {c['status']} | {c['time']:.2f} s |")
    lines += ["", "Archivo JUnit para herramientas de CI: [`junit.xml`](junit.xml)", ""]
    with open(os.path.join(TESTS_DIR, "resultado-pruebas.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def write_tests_html(summary, by_file, cases):
    rows = "".join(
        f"<tr><td><code>{html.escape(f['file'])}</code><br><small>{html.escape(f['label'])}</small></td>"
        f"<td class='n'>{f['total']}</td><td class='n ok'>{f['passed']}</td>"
        f"<td class='n {'bad' if f['failed'] else ''}'>{f['failed']}</td><td class='n'>{f['time']:.1f} s</td>"
        f"<td><div class='bar'><div style='width:{(f['passed'] / f['total'] * 100) if f['total'] else 0:.0f}%'></div></div></td></tr>"
        for f in by_file)
    slow = sorted(cases, key=lambda c: -c["time"])[:6]
    slow_rows = "".join(f"<li><code>{html.escape(c['name'])}</code><span>{c['time']:.1f} s</span></li>" for c in slow)
    rate = summary["passed"] / summary["total"] * 100 if summary["total"] else 0
    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    html,body{{overflow:hidden}} body{{margin:0;font-family:Segoe UI,Arial,sans-serif;background:#f1f5f9;color:#0f172a}}
    .wrap{{width:1100px;padding:36px}} h1{{margin:0 0 4px;font-size:28px}} .muted{{color:#64748b}}
    .cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:24px 0}}
    .card{{background:#fff;border-radius:12px;padding:18px 20px;border-top:4px solid #1e3a8a;box-shadow:0 1px 3px #0001}}
    .card b{{display:block;font-size:34px}} .card span{{color:#64748b;font-size:13px;font-weight:600;text-transform:uppercase}}
    .ok{{color:#16a34a}} .bad{{color:#dc2626}} .green{{border-top-color:#16a34a}} .red{{border-top-color:#dc2626}}
    .panel{{background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px #0001;margin-bottom:16px}}
    table{{width:100%;border-collapse:collapse}} th,td{{padding:10px;border-bottom:1px solid #e2e8f0;text-align:left;font-size:14px}}
    th{{font-size:12px;color:#64748b;text-transform:uppercase;background:#f8fafc}} .n{{text-align:right}}
    small{{color:#64748b}} .bar{{height:8px;background:#e2e8f0;border-radius:9px;overflow:hidden;width:160px}}
    .bar div{{height:100%;background:#16a34a}} ul{{list-style:none;margin:0;padding:0}}
    li{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #e2e8f0;font-size:14px}}
    h2{{font-size:17px;margin:0 0 12px}}</style></head><body><div class="wrap">
    <h1>QA Center · Resultado de las pruebas automatizadas</h1>
    <div class="muted">Ejecutado el {summary['date']} con pytest · unittest · Selenium</div>
    <div class="cards">
      <div class="card"><span>Pruebas</span><b>{summary['total']}</b></div>
      <div class="card green"><span>Exitosas</span><b class="ok">{summary['passed']}</b></div>
      <div class="card red"><span>Fallidas</span><b class="{'bad' if summary['failed'] else ''}">{summary['failed']}</b></div>
      <div class="card green"><span>Pass rate</span><b>{rate:.0f} %</b></div>
    </div>
    <div class="panel"><h2>Por archivo de pruebas</h2><table>
      <tr><th>Archivo</th><th class="n">Pruebas</th><th class="n">Exitosas</th><th class="n">Fallidas</th><th class="n">Tiempo</th><th></th></tr>
      {rows}</table></div>
    <div class="panel"><h2>Pruebas más largas</h2><ul>{slow_rows}</ul></div>
    </div></body></html>"""
    path = os.path.join(TESTS_DIR, "resultado-pruebas.html")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(page)
    return path


# ============================================================================= 2. reportes de ejemplo
BROKEN = b"""<!DOCTYPE html><html><head><title>Portal clientes</title>
<link rel="stylesheet" href="/estilos-faltantes.css"><script src="/app-faltante.js"></script></head>
<body style="font-family:Segoe UI;padding:40px"><h1>Portal de clientes (demo)</h1><a href="/pagos.html">Pagos</a>
<script>console.error("No se pudo cargar el perfil del usuario");
setTimeout(function(){ calcularTotal(); }, 100); fetch("/api/facturas");</script></body></html>"""
PAGOS = b"""<!DOCTYPE html><html><head><title>Pagos</title></head><body><h1>Pagos</h1>
<script>var cliente = null; cliente.nombre;</script></body></html>"""


class Site(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = {"/": BROKEN, "/pagos.html": PAGOS}.get(self.path)
        self.send_response(200 if body else 404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body or b"no encontrado")

    def log_message(self, *args):
        pass

    def handle(self):
        try:
            super().handle()
        except ConnectionResetError:
            pass


REPORTS = [
    ("01-informe-ejecutivo", "/reports/export?format={fmt}", "Informe ejecutivo de pruebas"),
    ("02-plan-de-pruebas", "/plans/1/report?format={fmt}", "Plan de pruebas"),
    ("03-casos-de-prueba", "/test-cases/report?format={fmt}", "Casos de prueba"),
    ("04-matriz-trazabilidad", "/rtm/report?format={fmt}", "Matriz de trazabilidad"),
    ("05-reporte-defectos", "/defects/report?format={fmt}", "Reporte de defectos"),
    ("06-analisis-url", "/scans/SCAN-1001/report?format={fmt}", "Análisis de URL (errores de consola)"),
]


def seed_demo(client, headers, demo_url):
    import automation
    import monitor

    def post(path, **kw):
        response = client.post("/api/v1" + path, headers=headers, **kw)
        assert response.status_code < 300, (path, response.status_code, response.get_data()[:300])
        return response.get_json()

    automation.run_system_tests(client.application)
    ana = post("/developers", json={"name": "Ana Torres", "email": "ana@empresa.com", "area": "Frontend"})
    luis = post("/developers", json={"name": "Luis Pérez", "email": "luis@empresa.com", "area": "Backend"})
    target = post("/targets", json={"name": "Portal clientes", "url": demo_url, "developer_id": ana["id"],
                                    "max_pages": 2, "monitor": True, "environment": "Local"})
    post("/test-runs", json={"tool": "Postman", "suite": "API Facturación", "environment": "QA", "total": 24,
                             "failed": 2, "module": "Facturación", "notes": "POST /facturas devuelve 500 con IVA 0"})
    post("/test-runs", json={"tool": "Selenium", "suite": "Regresión UI", "environment": "Staging", "total": 40,
                             "failed": 0, "skipped": 3, "module": "Portal"})
    monitor.start_scan(target["url"], "Admin QA", target_id=target["id"], max_pages=2, wait_seconds=1.5,
                       auto_incidents=True, wait=True)
    plan = post("/plans", json={
        "name": "Pruebas del módulo de facturación", "version": "1.2", "status": "En ejecución",
        "responsible": "Admin QA", "environment": "QA", "start_date": "2026-10-13", "end_date": "2026-10-31",
        "objective": "Validar la emisión, anulación y consulta de facturas antes del pase a producción.",
        "scope_in": "Emisión, anulación y consulta de facturas en el portal web y la API.",
        "scope_out": "Integración con el SRI y reportes contables.",
        "features": "Emitir factura\nAnular factura\nConsultar historial\nEnviar factura por correo",
        "approach": "Pruebas funcionales manuales, API con Postman, regresión de interfaz con Selenium y análisis "
                    "de errores de consola con QA Center.",
        "acceptance_criteria": "95 % de casos aprobados y 0 defectos críticos o altos abiertos.",
        "resources": "2 testers QA, ambiente QA con datos anonimizados, Postman, Selenium, QA Center.",
        "schedule": "Semana 1: diseño de casos\nSemana 2: ejecución\nSemana 3: regresión y cierre",
        "risks": "Retraso del ambiente QA; datos de prueba incompletos."})
    reqs = [post("/requirements", json={"code": code, "title": title, "kind": "Historia de usuario",
                                        "plan_id": plan["id"], "module": "Facturación", "priority": prio})
            for code, title, prio in (("HU-01", "Como cajero quiero emitir una factura", "Alta"),
                                      ("HU-02", "Como cajero quiero anular una factura", "Normal"),
                                      ("HU-03", "Como contador quiero consultar el historial", "Normal"),
                                      ("HU-04", "Como cliente quiero recibir la factura por correo", "Baja"))]
    cases = [("Emitir factura con datos válidos", 0, "Aprobado", "La factura FAC-0001 se emitió correctamente"),
             ("Emitir factura con IVA 0 %", 0, "Fallido", "Error 500: division by zero"),
             ("Anular factura del mismo día", 1, "Aprobado", "La factura quedó anulada"),
             ("Anular factura de un mes cerrado", 1, "Bloqueado", "No hay datos de un mes cerrado en QA"),
             ("Consultar historial por rango de fechas", 2, None, "")]
    for title, req, result, actual in cases:
        spec = post("/test-cases", json={
            "plan_id": plan["id"], "title": title, "module": "Facturación", "type": "Funcional",
            "preconditions": "Usuario cajero con sesión iniciada", "input_data": "Cliente 0912345678, 2 productos",
            "steps": "1. Ir a Facturación\n2. Completar los datos\n3. Pulsar Emitir",
            "expected": "La operación se completa y se muestra el número de factura",
            "requirement_ids": [reqs[req]["id"]]})
        if result:
            post(f"/test-cases/{spec['id']}/execute", json={
                "status": result, "actual": actual, "create_defect": result == "Fallido", "severity": "Alta",
                "developer_id": luis["id"]})


def export_reports(client, headers):
    import pypdfium2 as pdfium

    produced = []
    for slug, path, title in REPORTS:
        for fmt, ext in (("pdf", "pdf"), ("excel", "xlsx")):
            response = client.get("/api/v1" + path.format(fmt=fmt), headers=headers)
            assert response.status_code == 200, (path, fmt, response.status_code)
            file_path = os.path.join(EXAMPLES_DIR, f"{slug}.{ext}")
            with open(file_path, "wb") as fh:
                fh.write(response.data)
        pdf = pdfium.PdfDocument(os.path.join(EXAMPLES_DIR, f"{slug}.pdf"))
        page = pdf[0]
        image = page.render(scale=1.4).to_pil()
        image.save(os.path.join(PREVIEWS_DIR, f"{slug}.png"), optimize=True)
        produced.append((slug, title, len(pdf)))
        pdf.close()
    return produced


# ============================================================================= 3. capturas
SCREENS = [
    # (archivo, título, ruta #vista, acción opcional: abre un diálogo; None = página completa)
    ("01-resumen", "Resumen", "resumen", None),
    ("02-analizar-url", "Analizar URL: errores de consola, JavaScript y red", "analizador/SCAN-1001", None),
    ("03-resultados-postman-selenium", "Resultados de Postman / Selenium", "resultados", None),
    ("04-pruebas-automaticas", "Pruebas automáticas del sistema", "automaticas", None),
    ("05-plan-de-pruebas", "Plan de pruebas", "plan", None),
    ("06-plan-formulario", "Plan de pruebas: formulario", "plan", "#plan-list button[data-act='edit']"),
    ("07-casos-de-prueba", "Casos de prueba", "casos", None),
    ("08-caso-formulario", "Caso de prueba: formulario", "casos", "#table-cases button[data-act='edit']"),
    ("09-caso-ejecutar", "Caso de prueba: ejecutar y crear defecto", "casos",
     "#table-cases tbody tr:nth-child(2) button[data-act='execute']"),
    ("10-caso-detalle", "Caso de prueba: detalle, evidencias e historial", "casos",
     "#table-cases tbody tr:nth-child(2) [data-act='view']"),
    ("11-matriz-trazabilidad", "Matriz de trazabilidad (RTM)", "trazabilidad", None),
    ("12-reporte-defectos", "Reporte de defectos", "defectos", None),
    ("13-novedades", "Novedades", "novedades", None),
    ("14-novedad-detalle", "Novedad: detalle, envío al programador e historial", "novedades",
     "#table-incidents button[data-act='view']"),
    ("15-programadores", "Programadores", "programadores", None),
    ("16-aplicaciones", "Aplicaciones monitoreadas", "aplicaciones", None),
    ("17-reportes", "Reportes", "reportes", None),
    ("18-configuracion", "Configuración", "configuracion", None),
]
LOGIN_SCREEN = ("00-login", "Inicio de sesión")


def take_screenshots(base_url, tests_html):
    from selenium import webdriver
    from selenium.webdriver.common.by import By

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)

    def viewport(width, height):
        driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride",
                               {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})

    def full_page(path, width=1440, max_height=2400):
        viewport(width, 900)
        time.sleep(0.4)
        height = driver.execute_script("return Math.max(document.documentElement.scrollHeight, "
                                       "document.body.scrollHeight)")
        viewport(width, max(900, min(height, max_height)))
        time.sleep(0.6)
        driver.save_screenshot(path)

    try:
        # Imagen del resultado de las pruebas
        driver.get("file:///" + tests_html.replace("\\", "/"))
        full_page(os.path.join(TESTS_DIR, "resultado-pruebas.png"), width=1172)

        # Login
        viewport(1440, 900)
        driver.get(base_url + "/login")
        time.sleep(1)
        driver.save_screenshot(os.path.join(SCREENS_DIR, f"{LOGIN_SCREEN[0]}.png"))
        driver.find_element(By.ID, "btn-login").click()
        time.sleep(2.5)

        for name, _title, route, action in SCREENS:
            driver.execute_script("document.querySelectorAll('dialog[open]').forEach(function (d) { d.close(); });")
            viewport(1440, 900)
            driver.execute_script("window.location.hash = arguments[0];", route)
            time.sleep(2.2)
            driver.execute_script("window.scrollTo(0, 0);")
            if action:
                driver.find_element(By.CSS_SELECTOR, action).click()
                time.sleep(1.5)
                driver.save_screenshot(os.path.join(SCREENS_DIR, f"{name}.png"))
            else:
                full_page(os.path.join(SCREENS_DIR, f"{name}.png"))
    finally:
        driver.quit()
    write_gallery()


def write_gallery():
    """docs/capturas/README.md: galería con todas las pantallas."""
    lines = ["# Capturas de QA Center", "", "Generadas con datos de demostración por "
             "`python docs/reportes/generar_reportes.py`.", "",
             f"## {LOGIN_SCREEN[1]}", "", f"![{LOGIN_SCREEN[1]}]({LOGIN_SCREEN[0]}.png)", ""]
    for name, title, _route, _action in SCREENS:
        lines += [f"## {title}", "", f"![{title}]({name}.png)", ""]
    with open(os.path.join(SCREENS_DIR, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ============================================================================= main
def main():
    print("1/3 Ejecutando las pruebas automatizadas…")
    summary = run_tests()
    print(f"    {summary['passed']}/{summary['total']} exitosas")

    print("2/3 Generando reportes de ejemplo…")
    os.environ["QA_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="qa_reportes_"), "qa_reports.db")
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    with redirect_stdout(io.StringIO()):
        from app import create_app
        from werkzeug.serving import make_server
    app = create_app()
    client = app.test_client()
    with redirect_stdout(io.StringIO()):
        token = client.post("/api/v1/auth/login", json={"email": "admin@test.com",
                                                        "password": "SecurePassword123"}).get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    site = http.server.HTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with redirect_stdout(io.StringIO()):
            seed_demo(client, headers, f"http://127.0.0.1:{site.server_port}/")
            produced = export_reports(client, headers)
        for slug, title, pages in produced:
            print(f"    {slug}: {title} ({pages} pág.)")
        print("3/3 Capturando pantallas…")
        take_screenshots(f"http://127.0.0.1:{server.server_port}", os.path.join(TESTS_DIR, "resultado-pruebas.html"))
    finally:
        server.shutdown()
        site.shutdown()
    print("Listo: docs/reportes y docs/capturas")


if __name__ == "__main__":
    main()
