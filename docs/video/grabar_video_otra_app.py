"""Genera docs/video/qa-center-probar-otra-aplicacion.mp4: cómo probar OTRA aplicación desde QA Center.

Muestra la diferencia entre «Pruebas automáticas» (QA Center se prueba a sí mismo) y los menús
«Analizar URL» y «Aplicaciones» (prueban cualquier otra aplicación por su URL).

Levanta todo con bases temporales (no toca backend/data):
  * QA Center,
  * QA TestBoard (C:\\Users\\Pc\\Downloads\\qa-testboard) como ejemplo de aplicación sana,
  * una página de ejemplo con errores, para ver cómo se detectan y se convierten en novedades.

Requisitos extra (solo para grabar):  pip install imageio imageio-ffmpeg
Ejecutar desde la raíz del proyecto:    python docs/video/grabar_video_otra_app.py
"""
import http.server
import io
import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import urllib.request
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QA_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="qa_video_otra_"), "qa_reports.db")
sys.path.insert(0, os.path.join(ROOT, "backend"))
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-center-probar-otra-aplicacion.mp4")
TESTBOARD_DIR = os.environ.get("TESTBOARD_DIR", os.path.join(os.path.dirname(ROOT), "qa-testboard"))

import imageio.v2 as imageio  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from selenium import webdriver  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.support import expected_conditions as EC  # noqa: E402
from selenium.webdriver.support.ui import Select, WebDriverWait  # noqa: E402

with redirect_stdout(io.StringIO()):
    import automation  # noqa: E402
    from app import create_app  # noqa: E402
    from monitor import MonitorScheduler  # noqa: E402
    from werkzeug.serving import make_server  # noqa: E402

FPS = 2
WIDTH, SHOT_H, BAND_H = 1280, 800, 160
FONT_DIR = r"C:\Windows\Fonts"
BLUE, AMBER, DARK = (30, 58, 138), (245, 158, 11), (15, 23, 42)


def font(size, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), ("arialbd.ttf" if bold else "arial.ttf")):
        try:
            return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
        except OSError:
            continue
    return ImageFont.load_default()


F_STEP, F_TITLE, F_TEXT, F_BIG, F_H2 = font(20, True), font(28, True), font(22), font(54, True), font(36, True)
F_LOGO, F_BODY, F_BODYB = font(42, True), font(25), font(25, True)

# ----------------------------------------------------------------------------- página de ejemplo con errores
BROKEN = b"""<!DOCTYPE html><html><head><title>Portal clientes</title>
<link rel="stylesheet" href="/estilos-faltantes.css"><script src="/app-faltante.js"></script></head>
<body style="font-family:Segoe UI;padding:40px"><h1>Portal de clientes (demo)</h1>
<p>Aplicaci&oacute;n de ejemplo con errores a prop&oacute;sito.</p><a href="/pagos.html">Pagos</a>
<script>
console.error("No se pudo cargar el perfil del usuario");
setTimeout(function(){ calcularTotal(); }, 100);
fetch("/api/facturas");
</script></body></html>"""
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


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_testboard():
    """Arranca QA TestBoard con su propio entorno virtual y una base temporal. Devuelve (proceso, url)."""
    python = os.path.join(TESTBOARD_DIR, ".venv", *(("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")))
    if not os.path.isfile(python):
        raise SystemExit(f"No se encontró QA TestBoard en {TESTBOARD_DIR} (falta .venv). Define TESTBOARD_DIR.")
    port = free_port()
    db = os.path.join(tempfile.mkdtemp(prefix="testboard_video_"), "tb.db").replace("\\", "/")
    proc = subprocess.Popen([python, "-c", f"from app import create_app; create_app().run(port={port})"],
                            cwd=TESTBOARD_DIR, env=dict(os.environ, DATABASE_URL=f"sqlite:///{db}"),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        try:
            urllib.request.urlopen(url + "/api/health", timeout=1)
            return proc, url
        except OSError:
            time.sleep(0.25)
    proc.kill()
    raise SystemExit("QA TestBoard no arrancó")


# ----------------------------------------------------------------------------- grabación
class Recorder:
    def __init__(self, driver):
        self.driver = driver
        self.frames = []
        self.step = 0

    def _add(self, img, seconds):
        self.frames.extend([np.asarray(img.convert("RGB"))] * max(1, int(seconds * FPS)))

    def card(self, title, lines, seconds=6):
        img = Image.new("RGB", (WIDTH, SHOT_H + BAND_H), BLUE)
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((80, 80, 180, 180), 18, fill=(255, 255, 255))
        draw.text((130, 130), "QA", font=F_LOGO, fill=BLUE, anchor="mm")
        draw.text((80, 240), title, font=F_BIG, fill=(255, 255, 255))
        y = 340
        for line in lines:
            draw.text((80, y), line, font=F_TITLE, fill=(219, 234, 254))
            y += 52
        self._add(img, seconds)

    def compare_card(self, seconds=11):
        """Diapositiva: qué prueba cada menú."""
        img = Image.new("RGB", (WIDTH, SHOT_H + BAND_H), (245, 247, 250))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, WIDTH, 90), fill=BLUE)
        d.text((60, 45), "¿Qué menú uso?", font=F_H2, fill="white", anchor="lm")
        cols = [
            ("Pruebas automáticas", (100, 116, 139), "Prueba a QA CENTER mismo",
             ["21 casos de su propia API:", "login, tokens, métricas,", "reportes PDF/Excel/CSV.",
              "", "No sirve para otra app."]),
            ("Analizar URL", BLUE, "Prueba OTRA aplicación (1 vez)",
             ["Escribes la URL y pulsas", "«Analizar». Abre la app en", "Chrome y captura errores",
              "de consola, JavaScript y red.", "Genera PDF/Excel y novedades."]),
            ("Aplicaciones", (22, 101, 52), "Prueba OTRA aplicación (siempre)",
             ["Registras la URL una vez.", "Con «Monitorear» se analiza", "sola cada 30 minutos.",
              "Los errores van al", "programador responsable."]),
        ]
        for i, (name, color, sub, lines) in enumerate(cols):
            x = 50 + i * 400
            d.rounded_rectangle((x, 140, x + 370, 820), 16, fill="white", outline=(226, 232, 240), width=2)
            d.rounded_rectangle((x, 140, x + 370, 230), 16, fill=color)
            d.rectangle((x, 200, x + 370, 230), fill=color)
            d.text((x + 185, 185), name, font=F_TITLE, fill="white", anchor="mm")
            d.text((x + 24, 260), sub, font=F_BODYB, fill=(31, 41, 55))
            for j, line in enumerate(lines):
                d.text((x + 24, 320 + j * 44), line, font=F_BODY, fill=(71, 85, 105))
        d.text((60, 880), "En este video: probar QA TestBoard y una aplicación con errores desde QA Center.",
               font=F_BODY, fill=(31, 41, 55))
        self._add(img, seconds)

    def shot(self, title, text, seconds=5):
        self.step += 1
        png = self.driver.get_screenshot_as_png()
        screen = Image.open(io.BytesIO(png)).convert("RGB").resize((WIDTH, SHOT_H), Image.LANCZOS)
        img = Image.new("RGB", (WIDTH, SHOT_H + BAND_H), DARK)
        img.paste(screen, (0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, SHOT_H, WIDTH, SHOT_H + 6), fill=AMBER)
        draw.rounded_rectangle((30, SHOT_H + 26, 140, SHOT_H + 60), 8, fill=AMBER)
        draw.text((85, SHOT_H + 43), f"Paso {self.step}", font=F_STEP, fill=DARK, anchor="mm")
        draw.text((160, SHOT_H + 22), title, font=F_TITLE, fill=(255, 255, 255))
        for i, line in enumerate(textwrap.wrap(text, 105)[:3]):
            draw.text((32, SHOT_H + 72 + i * 28), line, font=F_TEXT, fill=(203, 213, 225))
        self._add(img, seconds)

    def save(self):
        writer = imageio.get_writer(OUTPUT, fps=FPS, codec="libx264", quality=8, pixelformat="yuv420p",
                                    macro_block_size=16)
        for frame in self.frames:
            writer.append_data(frame)
        writer.close()


def main():
    app = create_app()
    with redirect_stdout(io.StringIO()):
        automation.run_system_tests(app)
    # Igual que al iniciar con python backend/app.py: el monitoreo queda activo (primera revisión en 30 min,
    # para que en el video se vea el botón «Monitorear ahora»).
    monitor = MonitorScheduler(initial_delay_seconds=1800)
    app.extensions["qa_monitor"] = monitor
    monitor.start()
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    site = http.server.HTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    testboard, testboard_url = start_testboard()
    base = f"http://127.0.0.1:{server.server_port}"
    broken_url = f"http://127.0.0.1:{site.server_port}/"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1600,1000")
    options.add_argument("--force-device-scale-factor=1")
    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1600, 1000)
    wait = WebDriverWait(driver, 60)
    rec = Recorder(driver)
    by_id = lambda i: driver.find_element(By.ID, i)  # noqa: E731

    def mark(element):
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});"
                              "arguments[0].style.outline='4px solid #f59e0b';"
                              "arguments[0].style.outlineOffset='3px';", element)
        time.sleep(0.2)
        return element

    def unmark(element):
        driver.execute_script("arguments[0].style.outline='';", element)

    def click(element):
        mark(element)
        unmark(element)
        element.click()

    def fill(element_id, text):
        element = by_id(element_id)
        element.clear()
        element.send_keys(text)

    def menu(name):
        click(driver.find_element(By.CSS_SELECTOR, f"a[data-nav='{name}']"))
        wait.until(EC.visibility_of_element_located((By.ID, f"view-{name}")))
        time.sleep(1.2)
        driver.execute_script("window.scrollTo(0, 0)")

    def wait_scan():
        WebDriverWait(driver, 180).until(EC.text_to_be_present_in_element((By.ID, "scan-msg"), "terminado"))
        time.sleep(2)

    try:
        rec.card("Probar otra aplicación", ["con QA Center, paso a paso", "",
                                            "QA Center:    http://localhost:5000",
                                            "Usuario:        admin@test.com  /  SecurePassword123",
                                            "Ejemplo:        QA TestBoard (http://localhost:5055)"], 7)
        rec.compare_card()

        # --- Login
        driver.get(base + "/login")
        wait.until(EC.visibility_of_element_located((By.ID, "email")))
        mark(by_id("btn-login"))
        rec.shot("Entrar a QA Center", "Abre http://localhost:5000 e inicia sesión con admin@test.com y la contraseña "
                 "SecurePassword123 (vienen precargados).", 5)
        by_id("btn-login").click()
        wait.until(EC.url_contains("/dashboard"))
        time.sleep(2.5)

        # --- Pruebas automáticas = QA Center mismo
        menu("automaticas")
        click(by_id("btn-run-tests"))
        WebDriverWait(driver, 60).until(EC.text_to_be_present_in_element((By.ID, "run-tests-status"), "exitosos"))
        time.sleep(1.2)
        rec.shot("«Pruebas automáticas» prueba a QA Center", "Este botón ejecuta 21 casos contra la API del propio QA "
                 "Center (login, tokens, métricas y reportes). No prueba otras aplicaciones: para eso están «Analizar "
                 "URL» y «Aplicaciones».", 8)

        # --- La aplicación a probar debe estar encendida
        driver.get(testboard_url + "/")
        time.sleep(1.5)
        rec.shot("1) Enciende la aplicación que vas a probar", "Ejemplo: QA TestBoard. Ábrela en una terminal "
                 "(python app.py) y copia su dirección, aquí http://localhost:5055. QA Center la visitará igual que un "
                 "usuario.", 7)
        driver.get(base + "/dashboard")
        wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "a[data-nav='programadores']")))
        time.sleep(1.5)

        # --- Programador responsable
        menu("programadores")
        fill("dev-name", "Ana Torres")
        fill("dev-email", "ana@empresa.com")
        fill("dev-area", "Frontend")
        mark(by_id("btn-dev-save"))
        rec.shot("2) Registra al programador responsable", "En «Programadores» agrega a quien recibirá los errores "
                 "encontrados: nombre, correo y área. Es opcional, pero así las novedades llegan asignadas.", 6)
        unmark(by_id("btn-dev-save"))
        by_id("btn-dev-save").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "dev-msg"), "registrado"))
        time.sleep(0.8)

        # --- Analizar URL: TestBoard (sin errores)
        menu("analizador")
        fill("scan-url", testboard_url)
        fill("scan-pages", "5")
        mark(by_id("scan-url"))
        rec.shot("3) «Analizar URL»: escribe la dirección", "Pega la URL de la aplicación y elige cuántas páginas "
                 "recorrer (sigue los enlaces internos). Aquí: QA TestBoard, 5 páginas.", 6)
        unmark(by_id("scan-url"))
        click(by_id("btn-scan"))
        time.sleep(2)
        rec.shot("Analizando…", "QA Center abre la aplicación en Chrome (sin ventana), espera que cargue y escucha la "
                 "consola, los errores de JavaScript y cada petición de red.", 4)
        wait_scan()
        driver.execute_script("document.getElementById('scan-result').scrollIntoView({block:'start'})")
        time.sleep(0.6)
        rec.shot("Resultado: sin errores", "QA TestBoard pasó: 0 errores de consola, 0 de red, HTTP 200 y el tiempo de "
                 "carga. A la derecha, la captura de la página. Así se ve una aplicación sana.", 7)

        # --- Analizar URL: aplicación con errores
        driver.execute_script("window.scrollTo(0, 0)")
        fill("scan-url", broken_url)
        fill("scan-pages", "2")
        click(by_id("btn-scan"))
        wait_scan()
        driver.execute_script("document.getElementById('scan-result').scrollIntoView({block:'start'})")
        time.sleep(0.6)
        rec.shot("Resultado: aplicación con errores", "Con otra aplicación aparecen los problemas: console.error, una "
                 "función que no existe, un objeto nulo y archivos que responden 404. Cada uno se convierte en una "
                 "novedad (NOV-…).", 8)
        mark(by_id("btn-scan-pdf"))
        rec.shot("Descargar el reporte", "«PDF» o «XLSX» descarga el reporte del análisis con la captura y el detalle "
                 "de cada error, para enviarlo al equipo.", 5)
        unmark(by_id("btn-scan-pdf"))
        driver.execute_script("document.getElementById('table-scans').scrollIntoView({block:'center'})")
        time.sleep(0.5)
        rec.shot("Historial de análisis", "Cada análisis queda guardado: URL, estado, cantidad de errores y fecha. "
                 "Con el botón de la fila se vuelve a abrir.", 5)

        # --- Aplicaciones: registrar para monitoreo
        menu("aplicaciones")
        fill("target-name", "QA TestBoard")
        fill("target-url", testboard_url)
        fill("target-pages", "5")
        Select(by_id("target-developer")).select_by_index(1)
        fill("target-notes", "Gestor de casos de prueba (Flask)")
        mark(by_id("btn-target-save"))
        rec.shot("4) «Aplicaciones»: registrar para siempre", "Para no escribir la URL cada vez, regístrala aquí: "
                 "nombre, URL, páginas y responsable. Con «Monitorear automáticamente» marcado, QA Center la revisa "
                 "sola.", 7)
        unmark(by_id("btn-target-save"))
        by_id("btn-target-save").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "target-msg"), "registrada"))
        time.sleep(0.6)
        fill("target-name", "Portal clientes")
        fill("target-url", broken_url)
        fill("target-pages", "2")
        Select(by_id("target-developer")).select_by_index(1)
        by_id("btn-target-save").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "target-msg"), "registrada"))
        time.sleep(1)
        rec.shot("Aplicaciones registradas", "Puedes registrar todas las que quieras. La tabla muestra la URL, el "
                 "responsable, si se monitorea y el último análisis.", 6)

        mark(by_id("btn-monitor-run"))
        rec.shot("5) «Monitorear ahora»", "Analiza todas las aplicaciones marcadas en este momento. Si no lo pulsas, "
                 "igual se hace solo cada 30 minutos (se cambia en Configuración).", 6)
        unmark(by_id("btn-monitor-run"))
        by_id("btn-monitor-run").click()
        time.sleep(2)
        deadline = time.time() + 240
        while time.time() < deadline:
            menu("resumen")
            menu("aplicaciones")
            rows = driver.find_element(By.ID, "table-targets").text
            if "En curso" not in rows and "Nunca" not in rows:
                break
            time.sleep(4)
        time.sleep(1)
        driver.execute_script("window.scrollTo(0, 0)")
        time.sleep(0.5)
        rec.shot("Último análisis de cada aplicación", "QA TestBoard: «Sin errores» en verde. Portal clientes: "
                 "errores en rojo. El botón «Analizar» de cada fila lo repite cuando quieras.", 7)

        # --- Novedades
        menu("novedades")
        time.sleep(1)
        rec.shot("6) Los errores llegan a «Novedades»", "Cada error encontrado es una novedad con severidad, aplicación "
                 "y programador asignado. Los repetidos no se duplican: se suman a la misma novedad.", 7)
        click(driver.find_element(By.CSS_SELECTOR, "#table-incidents tbody tr button[data-act='view']"))
        wait.until(EC.visibility_of_element_located((By.ID, "dlg-detail")))
        time.sleep(1)
        rec.shot("Detalle para el programador", "Pasos para reproducir, resultado esperado y obtenido. Desde aquí se "
                 "envía por correo o webhook, o se copia el texto para pasarlo al programador.", 7)
        driver.find_element(By.CSS_SELECTOR, "#dlg-detail [data-close]").click()
        time.sleep(0.5)

        menu("configuracion")
        rec.shot("7) Ajustar el monitoreo", "En «Configuración» se cambia cada cuánto se revisan las aplicaciones, si "
                 "se crean y envían novedades solas, y el correo o webhook (Slack/Teams).", 6)

        rec.card("Resumen", ["1. Enciende la aplicación a probar y copia su URL",
                             "2. «Analizar URL»  →  prueba única con reporte PDF/Excel",
                             "3. «Aplicaciones»  →  registro + monitoreo automático",
                             "4. Los errores llegan a «Novedades» para el programador",
                             "", "«Pruebas automáticas» es solo para QA Center mismo."], 9)
    finally:
        driver.quit()
        server.shutdown()
        site.shutdown()
        testboard.kill()
        monitor.stop()
    rec.save()
    print(f"Video: {OUTPUT} · {len(rec.frames) / FPS:.0f} s · {rec.step} pasos")


if __name__ == "__main__":
    main()
