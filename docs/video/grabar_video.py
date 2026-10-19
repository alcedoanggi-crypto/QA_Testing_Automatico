"""Genera docs/video/qa-center-paso-a-paso.mp4: recorrido guiado de QA Center con subtítulos.

Usa una base de datos temporal (no toca backend/data) y una página de ejemplo con errores de consola.

Requisitos extra (solo para grabar):  pip install imageio imageio-ffmpeg
Ejecutar desde la raíz del proyecto:    python docs/video/grabar_video.py
"""
import http.server
import io
import os
import sys
import tempfile
import textwrap
import threading
import time
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QA_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="qa_video_"), "qa_reports.db")
sys.path.insert(0, os.path.join(ROOT, "backend"))
OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa-center-paso-a-paso.mp4")

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
    from werkzeug.serving import make_server  # noqa: E402

FPS = 2
WIDTH, SHOT_H, BAND_H = 1280, 800, 160
FONT_DIR = r"C:\Windows\Fonts"


def font(size, bold=False):
    for name in (("segoeuib.ttf" if bold else "segoeui.ttf"), ("arialbd.ttf" if bold else "arial.ttf")):
        try:
            return ImageFont.truetype(os.path.join(FONT_DIR, name), size)
        except OSError:
            continue
    return ImageFont.load_default()


F_STEP, F_TITLE, F_TEXT, F_BIG = font(20, True), font(28, True), font(22), font(54, True)
F_LOGO = font(42, True)

# ----------------------------------------------------------------------------- página de ejemplo con errores
BROKEN = b"""<!DOCTYPE html><html><head><title>Portal clientes</title>
<link rel="stylesheet" href="/estilos-faltantes.css"><script src="/app-faltante.js"></script></head>
<body style="font-family:Segoe UI;padding:40px"><h1>Portal de clientes (demo)</h1><p>Pagina de ejemplo con errores.</p>
<a href="/pagos.html">Pagos</a>
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
            pass  # Chrome cierra conexiones al terminar; no es un error


# ----------------------------------------------------------------------------- grabación
class Recorder:
    def __init__(self, driver):
        self.driver = driver
        self.frames = []
        self.step = 0

    def card(self, title, lines, seconds=5):
        img = Image.new("RGB", (WIDTH, SHOT_H + BAND_H), (30, 58, 138))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle((80, 80, 180, 180), 18, fill=(255, 255, 255))
        draw.text((130, 130), "QA", font=F_LOGO, fill=(30, 58, 138), anchor="mm")
        draw.text((80, 240), title, font=F_BIG, fill=(255, 255, 255))
        y = 340
        for line in lines:
            draw.text((80, y), line, font=F_TITLE, fill=(219, 234, 254))
            y += 52
        self._add(img, seconds)

    def shot(self, title, text, seconds=4.5):
        """Captura la pantalla con un subtítulo: número de paso, título y explicación."""
        self.step += 1
        png = self.driver.get_screenshot_as_png()
        screen = Image.open(io.BytesIO(png)).convert("RGB").resize((WIDTH, SHOT_H), Image.LANCZOS)
        img = Image.new("RGB", (WIDTH, SHOT_H + BAND_H), (15, 23, 42))
        img.paste(screen, (0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, SHOT_H, WIDTH, SHOT_H + 6), fill=(245, 158, 11))
        draw.rounded_rectangle((30, SHOT_H + 26, 140, SHOT_H + 60), 8, fill=(245, 158, 11))
        draw.text((44, SHOT_H + 29), f"Paso {self.step}", font=F_STEP, fill=(15, 23, 42))
        draw.text((160, SHOT_H + 22), title, font=F_TITLE, fill=(255, 255, 255))
        y = SHOT_H + 72
        for line in textwrap.wrap(text, 105)[:3]:
            draw.text((32, y), line, font=F_TEXT, fill=(203, 213, 225))
            y += 28
        self._add(img, seconds)

    def _add(self, img, seconds):
        frame = np.asarray(img)
        self.frames.extend([frame] * max(1, int(seconds * FPS)))

    def save(self):
        writer = imageio.get_writer(OUTPUT, fps=FPS, codec="libx264", quality=8, pixelformat="yuv420p",
                                    macro_block_size=16)
        for frame in self.frames:
            writer.append_data(frame)
        writer.close()


def main():
    app = create_app()
    with redirect_stdout(io.StringIO()):
        automation.run_system_tests(app)          # datos iniciales para el resumen
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    site = http.server.HTTPServer(("127.0.0.1", 0), Site)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    demo_url = f"http://127.0.0.1:{site.server_port}/"

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

    try:
        rec.card("QA Center", ["Recorrido paso a paso", "", "Usuario:      admin@test.com",
                               "Contraseña:  SecurePassword123", "Dirección:    http://127.0.0.1:5000",
                               "Carpeta:       C:\\Users\\Pc\\Downloads\\qa-center"], 7)

        # --- Login
        driver.get(base + "/login")
        wait.until(EC.visibility_of_element_located((By.ID, "email")))
        mark(by_id("email"))
        mark(by_id("password"))
        rec.shot("Iniciar sesión", "Abre http://127.0.0.1:5000. Escribe el usuario admin@test.com y la contraseña "
                 "SecurePassword123 (vienen precargados) y pulsa «Iniciar sesión».", 6)
        unmark(by_id("email"))
        unmark(by_id("password"))
        mark(by_id("btn-login"))
        rec.shot("Iniciar sesión", "El servidor valida la contraseña y devuelve un token JWT que el navegador guarda "
                 "para las siguientes peticiones.", 3)
        by_id("btn-login").click()
        wait.until(EC.url_contains("/dashboard"))
        time.sleep(2.5)
        rec.shot("Resumen", "La pantalla principal: pruebas ejecutadas, pass rate, novedades abiertas, análisis de URL y "
                 "avance de la documentación QA. A la izquierda está el menú con todos los módulos.", 6)

        # --- Programadores
        menu("programadores")
        fill("dev-name", "Ana Torres")
        fill("dev-email", "ana@empresa.com")
        fill("dev-area", "Frontend")
        mark(by_id("btn-dev-save"))
        rec.shot("Registrar programadores", "En «Programadores» registra al equipo que recibirá los errores: nombre, "
                 "correo y área. Pulsa «Guardar».")
        by_id("btn-dev-save").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "dev-msg"), "registrado"))
        time.sleep(0.8)
        rec.shot("Registrar programadores", "El programador aparece en la tabla. Desde ahí se puede editar o eliminar; "
                 "también muestra cuántas novedades abiertas tiene.")

        # --- Aplicaciones
        menu("aplicaciones")
        fill("target-name", "Portal clientes")
        fill("target-url", demo_url)
        Select(by_id("target-developer")).select_by_visible_text("Ana Torres · Frontend")
        fill("target-pages", "2")
        mark(by_id("btn-target-save"))
        rec.shot("Registrar la aplicación a probar", "En «Aplicaciones» guarda la URL de tu sistema (por ejemplo "
                 "http://localhost:3000) y su responsable. Con «Monitorear» activo, QA Center la revisa solo cada 30 min.")
        by_id("btn-target-save").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "target-msg"), "registrada"))
        time.sleep(0.8)

        # --- Analizar URL
        menu("analizador")
        Select(by_id("scan-target")).select_by_index(1)
        time.sleep(0.4)
        mark(by_id("btn-scan"))
        rec.shot("Analizar URL: detectar errores de consola", "Elige la aplicación o escribe la URL y pulsa «Analizar». "
                 "QA Center abre la página en Chrome y escucha la consola, los errores de JavaScript y la red.")
        by_id("btn-scan").click()
        time.sleep(1.5)
        rec.shot("Analizando…", "El análisis corre en segundo plano; la pantalla consulta el avance cada 1,5 segundos.", 3)
        WebDriverWait(driver, 120).until(EC.text_to_be_present_in_element((By.ID, "scan-msg"), "terminado"))
        time.sleep(2)
        driver.execute_script("document.getElementById('scan-result').scrollIntoView({block:'start'})")
        time.sleep(0.6)
        rec.shot("Resultado del análisis", "Aparecen los errores: console.error, funciones que no existen, objetos nulos y "
                 "archivos que responden 404. Cada error se convirtió en una novedad (NOV-…) asignada a Ana.", 7)
        mark(by_id("btn-scan-pdf"))
        rec.shot("Reporte del análisis", "Con «PDF» o «XLSX» descargas el reporte del análisis, con la captura de pantalla "
                 "y el detalle de cada error.")

        # --- Novedades
        menu("novedades")
        time.sleep(1)
        rec.shot("Novedades", "Aquí están los errores para los programadores, con severidad, estado y responsable. "
                 "Puedes filtrarlos, seleccionar varios y asignarlos, cambiarles el estado o eliminarlos.", 6)
        first = driver.find_element(By.CSS_SELECTOR, "#table-incidents tbody tr button[data-act='view']")
        click(first)
        wait.until(EC.visibility_of_element_located((By.ID, "dlg-detail")))
        time.sleep(1)
        rec.shot("Pasar la novedad al programador", "En el detalle están los pasos para reproducir, el resultado esperado y "
                 "el obtenido. A la derecha: enviar por correo o webhook, abrir en tu correo o copiar el texto.", 7)
        fill("detail-comment", "Por favor revisar antes del viernes")
        by_id("form-comment").find_element(By.TAG_NAME, "button").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "detail-history"), "viernes"))
        driver.execute_script("document.getElementById('detail-history').scrollIntoView({block:'center'})")
        time.sleep(0.5)
        rec.shot("Historial y comentarios", "Cada cambio, envío y comentario queda en el historial de la novedad.")
        driver.find_element(By.CSS_SELECTOR, "#dlg-detail [data-close]").click()
        time.sleep(0.5)

        # --- Resultados Postman / Selenium
        menu("resultados")
        Select(by_id("run-tool")).select_by_visible_text("Postman")
        fill("run-suite", "API Facturación")
        fill("run-module", "Facturación")
        fill("run-total", "24")
        fill("run-failed", "2")
        fill("run-notes", "POST /facturas devuelve 500 cuando el IVA es 0")
        mark(by_id("btn-register-run"))
        rec.shot("Registrar resultados de Postman o Selenium", "Las pruebas que haces aparte se registran aquí: "
                 "herramienta, suite, totales y observaciones. Las exitosas se calculan solas. También puedes importar "
                 "el archivo de Newman o de JUnit.", 6)
        by_id("btn-register-run").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "register-run-msg"), "registrada"))
        time.sleep(1)
        driver.execute_script("document.getElementById('table-results').scrollIntoView({block:'center'})")
        rec.shot("Resultados registrados", "Cada resultado se puede ver, editar o eliminar desde su fila, y suma a las "
                 "métricas del Resumen.")

        # --- Plan de pruebas
        menu("plan")
        click(by_id("btn-new-plan"))
        wait.until(EC.visibility_of_element_located((By.ID, "plan-name")))
        fill("plan-name", "Pruebas del módulo de facturación")
        fill("plan-objective", "Validar emisión y anulación de facturas antes del pase a producción")
        fill("plan-features", "Emitir factura\nAnular factura")
        fill("plan-acceptance", "95 % de casos aprobados y 0 defectos críticos abiertos")
        fill("plan-resources", "2 testers, ambiente QA, datos de prueba")
        fill("plan-schedule", "Semana 1: diseño de casos. Semana 2: ejecución")
        rec.shot("Plan de pruebas", "Define el alcance, las funciones a evaluar, los criterios de aceptación, los recursos "
                 "y el cronograma.", 6)
        by_id("btn-plan-save").click()
        wait.until(EC.invisibility_of_element_located((By.ID, "dlg-plan")))
        time.sleep(1.2)

        # --- Matriz de trazabilidad: requisito
        menu("trazabilidad")
        Select(by_id("rtm-plan")).select_by_index(1)
        time.sleep(0.8)
        fill("req-code", "HU-01")
        Select(by_id("req-kind")).select_by_visible_text("Historia de usuario")
        fill("req-title", "Como cajero quiero emitir una factura")
        mark(by_id("btn-req-save"))
        rec.shot("Matriz de trazabilidad: requisitos", "Registra los requisitos o historias de usuario del cliente. "
                 "La matriz mostrará qué casos cubren cada uno.")
        by_id("btn-req-save").click()
        wait.until(EC.text_to_be_present_in_element((By.ID, "table-rtm"), "HU-01"))
        time.sleep(1)
        rec.shot("Requisito sin cobertura", "Recién creado, el requisito aparece «Sin cobertura»: todavía no hay un caso "
                 "de prueba que lo valide. Con «+ Caso» se crea uno ya vinculado.")

        # --- Caso de prueba
        click(driver.find_element(By.CSS_SELECTOR, "#table-rtm button[data-act='new-case']"))
        wait.until(EC.visibility_of_element_located((By.ID, "case-title")))
        fill("case-title", "Emitir factura con IVA 0 %")
        fill("case-preconditions", "Cajero con sesión iniciada")
        fill("case-input", "Cliente 0912345678 · producto exento de IVA")
        fill("case-steps", "1. Ir a Facturación\n2. Agregar el producto\n3. Pulsar Emitir")
        fill("case-expected", "La factura se emite con IVA 0 y se muestra su número")
        rec.shot("Caso de prueba", "ID automático, precondiciones, datos de entrada, pasos a seguir y resultado esperado. "
                 "El requisito HU-01 ya viene marcado.", 6)
        by_id("btn-case-save").click()
        wait.until(EC.invisibility_of_element_located((By.ID, "dlg-case")))

        menu("casos")
        click(driver.find_element(By.CSS_SELECTOR, "#table-cases button[data-act='execute']"))
        wait.until(EC.visibility_of_element_located((By.ID, "dlg-execute")))
        driver.find_element(By.CSS_SELECTOR, "input[name='exec-status'][value='Fallido']").click()
        fill("exec-actual", "Error 500: division by zero")
        Select(by_id("exec-severity")).select_by_visible_text("Alta")
        Select(by_id("exec-developer")).select_by_visible_text("Ana Torres · Frontend")
        time.sleep(0.4)
        rec.shot("Ejecutar el caso", "Al ejecutar marcas el resultado. Si falla, describes lo obtenido, adjuntas "
                 "evidencias (capturas, logs) y se crea el reporte de defecto asignado al programador.", 7)
        by_id("btn-exec-save").click()
        wait.until(EC.invisibility_of_element_located((By.ID, "dlg-execute")))
        time.sleep(1.5)
        rec.shot("Caso fallido con su defecto", "El caso queda «Fallido» y enlazado a su defecto (NOV-…), que ya está en "
                 "Novedades para el programador.")

        menu("trazabilidad")
        time.sleep(1)
        rec.shot("La matriz se actualiza sola", "HU-01 pasa a «Con fallas». Cuando el caso se apruebe, quedará «Validado». "
                 "Así ninguna funcionalidad queda sin probar.")

        menu("defectos")
        time.sleep(1)
        rec.shot("Reporte de defectos", "El documento para los desarrolladores: pasos de reproducción, esperado vs. "
                 "obtenido e impacto según la severidad. Se descarga en PDF o Excel.", 6)

        # --- Reportes
        menu("reportes")
        click(by_id("btn-auto-report"))
        wait.until(EC.text_to_be_present_in_element((By.ID, "auto-report-msg"), "Generado"))
        time.sleep(1)
        rec.shot("Reportes", "Informe ejecutivo, novedades, casos, trazabilidad y defectos. El reporte automático se genera "
                 "solo cada día a las 18:00 (y se envía por correo si configuras SMTP).", 7)

        menu("configuracion")
        rec.shot("Configuración", "Intervalo de monitoreo, creación y envío automático de novedades, webhook de Slack/Teams, "
                 "correo SMTP y hora del reporte diario.", 6)

        menu("resumen")
        time.sleep(1.5)
        rec.shot("Todo se refleja en el Resumen", "Las tarjetas, el avance de la documentación y las novedades prioritarias "
                 "se actualizan con todo lo que hiciste.", 6)
        rec.card("¡Listo!", ["Carpeta: C:\\Users\\Pc\\Downloads\\qa-center", "Guía completa en docs\\README.md", "",
                             "Iniciar:  python backend/app.py", "Usuario:  admin@test.com",
                             "Clave:     SecurePassword123"], 6)
    finally:
        driver.quit()
        server.shutdown()
        site.shutdown()
    rec.save()
    print(f"Video: {OUTPUT} · {len(rec.frames) / FPS:.0f} s · {rec.step} pasos")


if __name__ == "__main__":
    main()
