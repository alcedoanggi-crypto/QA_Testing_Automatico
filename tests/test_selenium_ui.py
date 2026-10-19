"""Automatización E2E con Selenium WebDriver: Login -> menús de QA Center -> Reportes -> Logout.

Por defecto levanta el servidor Flask en un hilo y en un puerto libre, por lo que no
requiere iniciar la app manualmente. Variables de entorno opcionales:
    QA_BASE_URL=http://127.0.0.1:5000   Usa un servidor ya en ejecución.
    HEADLESS=0                          Abre Chrome en modo normal (visible).

Ejecutar (desde la raíz del proyecto):
    python -m pytest tests/test_selenium_ui.py -v -s
"""
import csv
import http.server
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

# Base de datos temporal: las pruebas no deben escribir en backend/data/qa_reports.db
os.environ.setdefault("QA_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="qa_reports_test_"), "qa_reports.db"))
BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

VALID_EMAIL = "admin@test.com"
VALID_PASSWORD = "SecurePassword123"
WAIT_TIMEOUT = 15
CSV_FILENAME = "reporte_pruebas.csv"


def step(message):
    print(f"  [E2E] {message}", flush=True)


class LiveServer:
    """Servidor Flask real ejecutándose en un hilo en segundo plano."""

    def __init__(self):
        from werkzeug.serving import make_server
        from app import create_app

        self._server = make_server("127.0.0.1", 0, create_app(), threaded=True)
        self.url = f"http://127.0.0.1:{self._server.server_port}"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._server.shutdown()
        self._thread.join(timeout=5)


def build_driver(download_dir):
    options = webdriver.ChromeOptions()
    if os.environ.get("HEADLESS", "1") != "0":
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,1000")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL"})
    options.add_experimental_option("prefs", {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    # Necesario para habilitar descargas en modo headless.
    driver.execute_cdp_cmd("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": download_dir})
    return driver


class SeleniumUITestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.server = None
        cls.base_url = os.environ.get("QA_BASE_URL", "").rstrip("/")
        if not cls.base_url:
            cls.server = LiveServer()
            cls.server.start()
            cls.base_url = cls.server.url
        cls.download_dir = tempfile.mkdtemp(prefix="qa_reports_downloads_")
        cls.driver = build_driver(cls.download_dir)
        cls.wait = WebDriverWait(cls.driver, WAIT_TIMEOUT, ignored_exceptions=(StaleElementReferenceException,))

    @classmethod
    def tearDownClass(cls):
        cls.driver.quit()
        if cls.server:
            cls.server.stop()
        shutil.rmtree(cls.download_dir, ignore_errors=True)

    def setUp(self):
        # Cada prueba parte sin sesión.
        self.driver.get(f"{self.base_url}/login")
        self.driver.execute_script("window.localStorage.clear();")
        self.driver.get(f"{self.base_url}/login")
        self.wait.until(EC.visibility_of_element_located((By.ID, "email")))

    # ------------------------------------------------------------------ helpers
    def login(self, email, password):
        email_input = self.driver.find_element(By.ID, "email")
        password_input = self.driver.find_element(By.ID, "password")
        email_input.clear()
        email_input.send_keys(email)
        password_input.clear()
        password_input.send_keys(password)
        self.driver.find_element(By.ID, "btn-login").click()

    def wait_for_metric(self, value_id):
        """Espera a que la tarjeta reemplace el placeholder '—' por un valor numérico."""
        def has_value(driver):
            text = driver.find_element(By.ID, value_id).text.strip()
            return text if text and text != "—" and any(ch.isdigit() for ch in text) else False
        return self.wait.until(has_value)

    def open_view(self, name):
        """Navega con el menú lateral y espera a que la vista quede visible."""
        self.driver.find_element(By.CSS_SELECTOR, f"a[data-nav='{name}']").click()
        return self.wait.until(EC.visibility_of_element_located((By.ID, f"view-{name}")))

    def table_rows(self):
        return self.driver.find_elements(By.CSS_SELECTOR, "#table-test-runs tbody tr[data-run-id]")

    def run_automatic_tests(self):
        """Pulsa #btn-run-tests y espera a que el lote quede registrado en el panel y la tabla."""
        rows_before = len(self.table_rows())
        self.open_view("automaticas")
        self.driver.find_element(By.ID, "btn-run-tests").click()
        WebDriverWait(self.driver, 60).until(
            EC.text_to_be_present_in_element((By.ID, "run-tests-status"), "casos exitosos"))
        self.wait.until(lambda d: len(self.table_rows()) > rows_before)
        return self.driver.find_element(By.ID, "run-tests-status").text

    def wait_for_download(self, filename):
        path = os.path.join(self.download_dir, filename)

        def downloaded(_driver):
            partial = [f for f in os.listdir(self.download_dir) if f.endswith(".crdownload")]
            return os.path.isfile(path) and os.path.getsize(path) > 0 and not partial
        WebDriverWait(self.driver, WAIT_TIMEOUT, poll_frequency=0.25).until(downloaded)
        time.sleep(0.2)  # margen para que Chrome cierre el handle del archivo
        return path

    # ------------------------------------------------------------------ tests
    def test_01_full_flow_login_dashboard_export_logout(self):
        driver = self.driver

        step("1. Navegador inicializado y pantalla de login cargada")
        self.assertIn("/login", driver.current_url)

        step("2. Ingresando credenciales válidas y haciendo clic en #btn-login")
        self.login(VALID_EMAIL, VALID_PASSWORD)

        step("3. Esperando la carga de /dashboard")
        self.wait.until(EC.url_contains("/dashboard"))
        token = driver.execute_script("return window.localStorage.getItem('qa_token');")
        self.assertTrue(token, "El token JWT no se guardó en localStorage")

        step("4. Verificando que las tarjetas de métricas contengan valores visibles")
        for card_id, value_id in (
            ("card-total-tests", "value-total-tests"),
            ("card-pass-rate", "value-pass-rate"),
            ("card-bugs-found", "value-bugs-found"),
        ):
            card = self.wait.until(EC.visibility_of_element_located((By.ID, card_id)))
            value = self.wait_for_metric(value_id)
            self.assertTrue(card.is_displayed())
            step(f"   #{card_id}: {value}")
        self.assertIn("%", driver.find_element(By.ID, "value-pass-rate").text)

        step("5. Ejecutando las pruebas automáticas del sistema con #btn-run-tests")
        status = self.run_automatic_tests()
        step(f"   {status}")
        self.assertIn("/", status)
        cases = self.wait.until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "#last-run-cases li.case") or False)
        self.assertGreater(len(cases), 0, "El panel no muestra los casos de la última ejecución")
        self.assertEqual(driver.find_elements(By.CSS_SELECTOR, "#last-run-cases li.case-failed"), [],
                         "Hay casos automáticos fallidos")
        self.open_view("resumen")
        rows = self.table_rows()
        self.assertGreater(len(rows), 0, "La tabla de ejecuciones está vacía")
        self.wait_for_metric("value-total-tests")
        self.assertNotEqual(driver.find_element(By.ID, "value-total-tests").text, "0")

        step("6. Exportando reporte CSV con #btn-export-csv (menú Reportes)")
        self.open_view("reportes")
        driver.find_element(By.ID, "btn-export-csv").click()
        self.wait.until(EC.text_to_be_present_in_element((By.ID, "export-status"), "descargado"))
        csv_path = self.wait_for_download(CSV_FILENAME)
        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            content = list(csv.reader(fh))
        self.assertEqual(content[0][0], "ID Ejecución")
        self.assertIn("Pass Rate (%)", content[0])
        # >= porque el backend simula nuevas ejecuciones cada 30 s entre la carga y la exportación.
        self.assertGreaterEqual(len(content) - 1, len(rows), "El CSV tiene menos filas que la tabla")
        step(f"   Archivo descargado: {csv_path} ({len(content) - 1} filas)")

        step("7. Cerrando sesión con #btn-logout")
        driver.find_element(By.ID, "btn-logout").click()
        self.wait.until(EC.url_contains("/login"))
        self.wait.until(EC.visibility_of_element_located((By.ID, "btn-login")))
        token = driver.execute_script("return window.localStorage.getItem('qa_token');")
        self.assertIsNone(token, "El token no se eliminó al cerrar sesión")
        step("   Retorno a /login verificado")

    def test_02_invalid_credentials_show_error_message(self):
        self.login(VALID_EMAIL, "ClaveIncorrecta!")
        error = self.wait.until(EC.visibility_of_element_located((By.ID, "login-error-msg")))
        self.assertEqual(error.text, "Credenciales inválidas")
        self.assertIn("/login", self.driver.current_url)

    def test_03_dashboard_without_token_redirects_to_login(self):
        self.driver.get(f"{self.base_url}/dashboard")
        self.wait.until(EC.url_contains("/login"))
        self.assertTrue(self.driver.find_element(By.ID, "email").is_displayed())

    def test_04_table_filter_by_status(self):
        self.login(VALID_EMAIL, VALID_PASSWORD)
        self.wait.until(EC.url_contains("/dashboard"))
        self.wait_for_metric("value-total-tests")
        if not self.table_rows():
            self.run_automatic_tests()
        self.open_view("resumen")

        self.driver.find_element(By.CSS_SELECTOR, "#filter-status option[value='Passed']").click()
        statuses = [el.text for el in self.driver.find_elements(By.CSS_SELECTOR, "#table-test-runs .status")]
        self.assertTrue(all(s == "Passed" for s in statuses), f"Filtro incorrecto: {statuses}")


    def test_05_register_manual_run_from_form(self):
        self.login(VALID_EMAIL, VALID_PASSWORD)
        self.wait.until(EC.url_contains("/dashboard"))
        self.wait_for_metric("value-total-tests")
        self.open_view("resultados")

        suite_input = self.driver.find_element(By.ID, "run-suite")
        suite_input.send_keys("Regresión E2E")
        for field_id, value in (("run-total", "40"), ("run-failed", "3"), ("run-skipped", "2")):
            field = self.driver.find_element(By.ID, field_id)
            field.clear()
            field.send_keys(value)
        self.assertEqual(self.driver.find_element(By.ID, "run-passed-preview").text, "35")
        self.driver.find_element(By.ID, "btn-register-run").click()

        self.wait.until(EC.text_to_be_present_in_element((By.ID, "register-run-msg"), "registrada"))
        result_row = self.wait.until(lambda d: next((r for r in d.find_elements(
            By.CSS_SELECTOR, "#table-results tbody tr[data-result-id]") if "Regresión E2E" in r.text), False))
        self.assertIn("Failed", result_row.text)

        self.open_view("resumen")
        row = self.wait.until(lambda d: next(
            (r for r in self.table_rows() if "Regresión E2E" in r.text), False))
        self.assertIn("Registro manual", row.text)

    def test_06_register_manual_run_validation(self):
        self.login(VALID_EMAIL, VALID_PASSWORD)
        self.wait.until(EC.url_contains("/dashboard"))
        self.wait_for_metric("value-total-tests")
        self.open_view("resultados")

        self.driver.find_element(By.ID, "run-suite").send_keys("Inválida")
        failed = self.driver.find_element(By.ID, "run-failed")
        failed.clear()
        failed.send_keys("99")
        self.driver.find_element(By.ID, "btn-register-run").click()
        self.wait.until(EC.text_to_be_present_in_element((By.ID, "register-run-msg"), "no puede superar"))

    def test_07_edit_and_delete_registered_result(self):
        self.login(VALID_EMAIL, VALID_PASSWORD)
        self.wait.until(EC.url_contains("/dashboard"))
        self.open_view("resultados")
        self.driver.find_element(By.ID, "run-suite").send_keys("Editar E2E")
        self.driver.find_element(By.ID, "btn-register-run").click()
        self.wait.until(EC.text_to_be_present_in_element((By.ID, "register-run-msg"), "registrada"))

        def result_row(text):
            return lambda d: next((r for r in d.find_elements(
                By.CSS_SELECTOR, "#table-results tbody tr[data-result-id]") if text in r.text), False)

        row = self.wait.until(result_row("Editar E2E"))
        row.find_element(By.CSS_SELECTOR, "button[data-act='edit']").click()
        suite = self.driver.find_element(By.ID, "run-suite")
        self.assertEqual(suite.get_attribute("value"), "Editar E2E")
        suite.clear()
        suite.send_keys("Editada E2E")
        self.driver.find_element(By.ID, "btn-register-run").click()
        self.wait.until(EC.text_to_be_present_in_element((By.ID, "register-run-msg"), "actualizada"))

        row = self.wait.until(result_row("Editada E2E"))
        row.find_element(By.CSS_SELECTOR, "button[data-act='delete']").click()
        self.wait.until(EC.element_to_be_clickable((By.ID, "btn-confirm-yes"))).click()
        self.wait.until(lambda d: not result_row("Editada E2E")(d))

    def test_08_scan_url_detects_console_errors(self):
        handler = type("Handler", (http.server.BaseHTTPRequestHandler,), {
            "do_GET": lambda h: (h.send_response(200 if h.path == "/" else 404),
                                 h.send_header("Content-Type", "text/html; charset=utf-8"), h.end_headers(),
                                 h.wfile.write(BROKEN_PAGE if h.path == "/" else b"no")),
            "log_message": lambda *a: None,
        })
        site = http.server.HTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=site.serve_forever, daemon=True).start()
        try:
            self.login(VALID_EMAIL, VALID_PASSWORD)
            self.wait.until(EC.url_contains("/dashboard"))
            self.open_view("analizador")
            self.driver.find_element(By.ID, "scan-url").send_keys(f"http://127.0.0.1:{site.server_port}/")
            self.driver.find_element(By.ID, "scan-wait").clear()
            self.driver.find_element(By.ID, "scan-wait").send_keys("1")
            self.driver.find_element(By.ID, "btn-scan").click()
            WebDriverWait(self.driver, 90).until(
                EC.text_to_be_present_in_element((By.ID, "scan-msg"), "terminado"))
            self.assertEqual(self.driver.find_element(By.ID, "scan-result-status").text, "Con errores")
            issues = self.driver.find_element(By.ID, "table-scan-issues").text
            step(f"   Errores detectados: {self.driver.find_element(By.ID, 'scan-stat-errors').text} JS/consola, "
                 f"{self.driver.find_element(By.ID, 'scan-stat-network').text} de red")
            self.assertIn("Error E2E de consola", issues)
            self.assertIn("ReferenceError", issues)
            self.assertIn("HTTP 404", issues)
            self.assertIn("NOV-", issues, "Las novedades automáticas deben quedar enlazadas")
        finally:
            site.shutdown()

    def test_09_incident_crud_from_dialog(self):
        self.login(VALID_EMAIL, VALID_PASSWORD)
        self.wait.until(EC.url_contains("/dashboard"))
        self.open_view("novedades")
        self.driver.find_element(By.ID, "btn-new-incident").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "inc-title"))).send_keys("Novedad E2E")
        self.driver.find_element(By.ID, "inc-actual").send_keys("Aparece un 500")
        self.driver.find_element(By.ID, "btn-inc-save").click()

        def incident_row(d):
            return next((r for r in d.find_elements(By.CSS_SELECTOR, "#table-incidents tbody tr[data-incident-id]")
                         if "Novedad E2E" in r.text), False)

        row = self.wait.until(incident_row)
        row.find_element(By.CSS_SELECTOR, "button[data-act='view']").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "dlg-detail")))
        self.assertEqual(self.driver.find_element(By.ID, "detail-title").text, "Novedad E2E")
        self.driver.find_element(By.ID, "detail-comment").send_keys("Revisado por QA")
        self.driver.find_element(By.CSS_SELECTOR, "#form-comment button").click()
        self.wait.until(EC.text_to_be_present_in_element((By.ID, "detail-history"), "Revisado por QA"))

        self.driver.find_element(By.ID, "btn-detail-delete").click()
        self.wait.until(EC.element_to_be_clickable((By.ID, "btn-confirm-yes"))).click()
        self.wait.until(EC.invisibility_of_element_located((By.ID, "dlg-detail")))
        self.wait.until(lambda d: not incident_row(d))

    def test_10_test_documentation_flow(self):
        """Plan -> requisito -> caso -> ejecución fallida -> defecto -> trazabilidad."""
        driver = self.driver
        self.login(VALID_EMAIL, VALID_PASSWORD)
        self.wait.until(EC.url_contains("/dashboard"))

        step("Plan de pruebas")
        self.open_view("plan")
        driver.find_element(By.ID, "btn-new-plan").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "plan-name"))).send_keys("Plan E2E")
        driver.find_element(By.ID, "plan-features").send_keys("Login")
        driver.find_element(By.ID, "plan-acceptance").send_keys("100 % de casos aprobados")
        driver.find_element(By.ID, "btn-plan-save").click()
        card = self.wait.until(lambda d: next((c for c in d.find_elements(By.CSS_SELECTOR, ".plan-card")
                                               if "Plan E2E" in c.text), False))
        self.assertIn("Cobertura de requisitos", card.text)

        step("Requisito en la matriz de trazabilidad")
        self.open_view("trazabilidad")
        driver.find_element(By.ID, "req-code").send_keys("HU-E2E")
        driver.find_element(By.ID, "req-title").send_keys("Como usuario quiero iniciar sesión")
        driver.find_element(By.ID, "btn-req-save").click()
        row = self.wait.until(lambda d: next((r for r in d.find_elements(By.CSS_SELECTOR, "#table-rtm tbody tr")
                                              if "HU-E2E" in r.text), False))
        self.assertIn("Sin cobertura", row.text)

        step("Caso de prueba creado desde el requisito")
        row.find_element(By.CSS_SELECTOR, "button[data-act='new-case']").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "case-title"))).send_keys("Login E2E")
        driver.find_element(By.ID, "case-preconditions").send_keys("Usuario registrado")
        driver.find_element(By.ID, "case-steps").send_keys("1. Abrir login")
        driver.find_element(By.ID, "case-expected").send_keys("Ingresa al dashboard")
        driver.find_element(By.ID, "btn-case-save").click()
        self.wait.until(EC.invisibility_of_element_located((By.ID, "dlg-case")))
        self.wait.until(lambda d: "Pendiente" in d.find_element(By.ID, "table-rtm").text)

        step("Ejecución fallida con evidencia y defecto")
        self.open_view("casos")
        case_row = self.wait.until(lambda d: next((r for r in d.find_elements(By.CSS_SELECTOR, "#table-cases tbody tr")
                                                   if "Login E2E" in r.text), False))
        case_row.find_element(By.CSS_SELECTOR, "button[data-act='execute']").click()
        self.wait.until(EC.visibility_of_element_located((By.ID, "dlg-execute")))
        driver.find_element(By.CSS_SELECTOR, "input[name='exec-status'][value='Fallido']").click()
        driver.find_element(By.ID, "exec-actual").send_keys("Error 500 al ingresar")
        evidence = os.path.join(self.download_dir, "consola_e2e.log")
        with open(evidence, "w", encoding="utf-8") as fh:
            fh.write("TypeError: x is undefined")
        driver.find_element(By.ID, "exec-files").send_keys(evidence)
        driver.find_element(By.ID, "btn-exec-save").click()
        self.wait.until(EC.invisibility_of_element_located((By.ID, "dlg-execute")))
        case_row = self.wait.until(lambda d: next((r for r in d.find_elements(By.CSS_SELECTOR, "#table-cases tbody tr")
                                                   if "Login E2E" in r.text and "NOV-" in r.text), False))
        self.assertIn("Fallido", case_row.text)

        step("Trazabilidad con fallas y reporte de defectos")
        self.open_view("trazabilidad")
        self.wait.until(lambda d: "Con fallas" in d.find_element(By.ID, "table-rtm").text)
        self.open_view("defectos")
        self.wait.until(lambda d: "Login E2E" in d.find_element(By.ID, "defect-list").text)
        self.assertIn("Error 500 al ingresar", driver.find_element(By.ID, "defect-list").text)

    def test_11_all_menus_without_console_errors(self):
        """Recorre todos los menús y verifica que QA Center no deje errores en la consola del navegador."""
        self.login(VALID_EMAIL, VALID_PASSWORD)
        self.wait.until(EC.url_contains("/dashboard"))
        self.wait_for_metric("value-total-tests")
        self.driver.get_log("browser")  # descarta lo anterior al inicio de sesión
        views = [a.get_attribute("data-nav") for a in self.driver.find_elements(By.CSS_SELECTOR, "a[data-nav]")]
        self.assertGreaterEqual(len(views), 13)
        for view in views:
            self.open_view(view)
            time.sleep(0.4)
        errors = [e["message"] for e in self.driver.get_log("browser") if e["level"] == "SEVERE"]
        step(f"   Menús recorridos: {len(views)} · errores de consola: {len(errors)}")
        self.assertEqual(errors, [], "Errores en la consola del navegador")


BROKEN_PAGE = b"""<!DOCTYPE html><html><head><title>Sitio roto</title><script src="/falta.js"></script></head>
<body><h1>Demo</h1><script>console.error("Error E2E de consola"); funcionQueNoExiste();</script></body></html>"""


if __name__ == "__main__":
    unittest.main(verbosity=2)
