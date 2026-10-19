# 3. Lógica de los módulos

Cada sección explica **qué hace** el módulo, **cómo lo hace** y **por qué** se hizo así.

---

## 3.1 Analizador de URL: capturar los errores de la consola

Archivo: `backend/url_scanner.py`.

### El problema

Los errores de consola solo existen **cuando la página se ejecuta en un navegador**. Descargar el HTML con una
petición normal no basta: el JavaScript no corre y no hay consola. Por eso el analizador abre **Chrome de verdad**,
sin ventana (*headless*), controlado por Selenium.

### Las tres fuentes de errores

```
                        ┌─────────────────────────────┐
  driver.get(url) ───▶  │   Chrome sin interfaz       │
                        │                             │
  1. Gancho JS ────────▶│  console.error / warn       │──▶ window.__qaIssues
     (inyectado antes   │  window.onerror             │
      de la página)     │  unhandledrejection         │
                        │                             │
  2. Log de red ◀───────│  Network.responseReceived   │  (HTTP ≥ 400)
     ("performance")    │  Network.loadingFailed      │  (sin conexión, CORS…)
                        │                             │
  3. Log del navegador ◀│  CSP, contenido mixto…      │
                        └─────────────────────────────┘
```

**1. Un gancho de JavaScript inyectado antes de la página.** Con el protocolo de Chrome DevTools (CDP) se registra un
script que corre **antes que cualquier script de la aplicación**:

```python
driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": CAPTURE_HOOK})
```

El gancho reemplaza `console.error` y `console.warn` por versiones que **guardan el mensaje y luego llaman al
original** (la consola sigue funcionando normal), y escucha los errores no capturados:

```javascript
["error", "warn"].forEach(function (method) {
  var original = console[method];
  console[method] = function () {
    push(method === "error" ? "error" : "warning", "console", text(arguments));
    return original.apply(this, arguments);       // la app no nota la diferencia
  };
});
window.addEventListener("error", function (e) { ... }, true);              // excepciones y recursos
window.addEventListener("unhandledrejection", function (e) { ... });       // promesas sin catch
```

Al terminar de cargar, Python lee lo guardado: `driver.execute_script("return window.__qaIssues || [];")`.

**2. El log de red.** Al crear Chrome se activa el registro de rendimiento:

```python
options.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})
```

`driver.get_log("performance")` devuelve los eventos de red de DevTools. `_network_issues()` los recorre:
`Network.requestWillBeSent` (para saber la URL de cada petición), `Network.responseReceived` con `status >= 400`
(404, 500…) y `Network.loadingFailed` (servidor caído, CORS, DNS). Así se detecta el `fetch("/api/datos")` que
responde 404, aunque la aplicación no escriba nada en la consola.

**3. El log del navegador** (`driver.get_log("browser")`) para mensajes que solo emite Chrome, como violaciones de
seguridad (CSP). Se descartan los que ya cubren las fuentes 1 y 2 para no duplicar.

### Detalles que hacen que funcione bien

- **Espera tras cargar** (`wait_seconds`, 2 s por defecto): muchos errores ocurren después de la carga (un `fetch`, un
  `setTimeout`). Sin esta espera se perderían.
- **Recorrer varias páginas** (`max_pages`): después de la primera página se leen los enlaces `<a href>` del mismo
  sitio y se visitan en cola, evitando repetir, archivos (`.pdf`, `.zip`…) y enlaces de `logout`.
- **Quitar duplicados** (`_dedupe`): el mismo mensaje del mismo recurso se guarda una sola vez por página.
- **Captura de pantalla** de la primera página (`driver.save_screenshot`) para la evidencia.
- **Un Chrome a la vez** (`_driver_lock`) y siempre se cierra en `finally: driver.quit()`, aunque algo falle.
- **Plan B sin navegador** (`scan_with_http`): si Chrome no está instalado, descarga el HTML, busca los `<script>`,
  `<link>` e `<img>` y revisa si responden con error. Avisa que en este modo no ve errores de JavaScript.

### Probarlo solo (como se hizo al construirlo)

```python
from url_scanner import scan_url
r = scan_url("http://localhost:3000", max_pages=2, wait_seconds=1.5)
for i in r["issues"]:
    print(i["level"], i["source"], i["message"])
```

---

## 3.2 Análisis en segundo plano

Archivo: `backend/monitor.py` (`start_scan`, `_run_scan`).

Un análisis tarda varios segundos. Si la petición HTTP esperara, el navegador quedaría colgado. Solución:

```
Navegador                         Servidor
   │ POST /api/v1/scans  ───────▶  crea el análisis en estado "En curso"
   │ ◀──── 202 {scan_id}           lo manda a un hilo (ThreadPoolExecutor) y responde YA
   │
   │ GET /api/v1/scans/SCAN-1001  (cada 1,5 s)
   │ ◀──── {status: "En curso"}
   │ GET /api/v1/scans/SCAN-1001
   │ ◀──── {status: "Con errores", issues: [...]}   → la pantalla muestra el resultado
```

```python
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="qa-scan")

def start_scan(url, executed_by, ..., wait=False):
    scan = store.create_scan(url, target_id, executed_by, trigger)   # "En curso"
    if wait:
        return _run_scan(...)          # el monitoreo y las pruebas esperan el resultado
    _executor.submit(_run_scan, ...)   # la pantalla no espera
    return scan
```

El código **202 Accepted** significa "recibido, se está procesando". La técnica de preguntar cada cierto tiempo se
llama *polling* (en `scanner.js`, función `waitForScan`).

`_run_scan` envuelve todo en `try/except`: si algo inesperado falla, el análisis queda en "Error" con el mensaje,
**nunca** "En curso" para siempre.

---

## 3.3 Novedades: de un error a un defecto asignado

Archivos: `backend/qa_store.py` (datos), `backend/monitor.py` (creación automática).

### Ciclo de vida

```
Nueva ──(se asigna)──▶ Asignada ──▶ En progreso ──▶ Resuelta ──▶ Verificada ──▶ Cerrada
                                                       │
                                     (el error vuelve) ▼
                                                   Reabierta
```

Estados "abiertos": Nueva, Asignada, En progreso y Reabierta (`OPEN_STATUSES`). Al asignar un programador a una
novedad "Nueva", pasa sola a "Asignada".

### Historial automático

Cada cambio queda registrado en `incident_history`. `update_incident` compara el antes y el después de los campos
importantes y escribe el detalle:

```python
labels = {"status": "Estado", "severity": "Severidad", "developer_id": "Asignado a", ...}
for key, label in labels.items():
    if nuevo[key] != actual[key]:
        cambios.append(f"{label}: {actual[key]} → {nuevo[key]}")      # "Estado: Nueva → Resuelta"
```

### No duplicar: la huella (*fingerprint*)

Si una aplicación se monitorea cada 30 minutos y tiene el mismo error, no queremos 48 novedades al día. Cada error
recibe una **huella**: un resumen de "en qué página, de qué tipo y qué mensaje":

```python
def issue_fingerprint(page_url, source, message):
    parts = urlsplit(page_url)
    page = f"{parts.netloc}{parts.path}"                       # sin ?parámetros
    normalized = re.sub(r"\d+", "#",                           # los números no importan
                        re.sub(r"\?[^\s'\"]*", "", message.lower()))
    return hashlib.sha1(f"{page}|{source}|{normalized}".encode()).hexdigest()
```

Los números se reemplazan por `#` porque el mismo error suele cambiar de número de línea entre versiones
(`app.js:10:5` → `app.js:11:7`). Antes de crear una novedad se busca una **abierta** con la misma huella:

- **No existe** → se crea la novedad.
- **Existe** → se suma 1 a "Veces detectada" y se anota "Reaparición" en el historial. Si estaba "Resuelta", se
  **reabre**: el programador dijo que lo arregló, pero el error volvió.

### Severidad automática

`_severity_for(issue)` decide la severidad inicial: excepciones de JavaScript → **Alta**; errores HTTP 5xx o página
que no carga → **Alta**; 404 de un recurso → **Media**; advertencias → **Baja**. QA puede cambiarla después.

### Responsable automático

Si el análisis es de una **Aplicación** registrada con programador responsable, las novedades se le asignan a él.

---

## 3.4 Notificaciones: pasar la novedad al programador

Archivo: `backend/notifier.py`.

`build_message()` arma un texto con todo lo necesario para reproducir y corregir (severidad, URL, pasos, esperado,
obtenido, enlace a QA Center). Luego hay cuatro canales:

| Canal | Cómo funciona | Requiere |
|---|---|---|
| Correo | `smtplib` se conecta al servidor SMTP, inicia TLS, se autentica y envía | Configurar SMTP |
| Webhook | `POST` con JSON a la URL del canal de Slack, Teams o Discord | URL del webhook |
| Mi correo | Enlace `mailto:` que abre tu programa de correo con el texto listo | Nada |
| Copiar texto | Copia el mensaje al portapapeles | Nada |

El JSON del webhook incluye dos campos para ser compatible con varias plataformas:

```python
payload = json.dumps({"text": text, "content": text[:1990]})
# "text" lo leen Slack y Teams; "content" lo lee Discord (máximo 2000 caracteres)
```

`notify_incident()` intenta cada canal por separado y devuelve el resultado de cada uno
(`{"email": "ok", "webhook": "No se pudo contactar…"}`): si uno falla, los otros siguen. Todo queda en el historial,
incluidos los errores de envío.

---

## 3.5 Resultados de Postman / Selenium

Archivos: `backend/reports_engine.py`, `backend/importers.py`.

### Cálculos de una ejecución

`build_run_record()` recibe lo que escribes y calcula el resto, para que nunca haya datos inconsistentes:

```python
passed    = total - failed - skipped
status    = "Passed" if failed == 0 else "Failed"
pass_rate = round(passed / total * 100, 2)
```

Y `validate_run_payload()` impide combinaciones imposibles: `total >= 1`, números enteros no negativos y
`failed + skipped <= total` ("Fallidas + Omitidas no puede superar el total").

### Importar un reporte de Newman (Postman)

Newman genera un JSON con `run.executions`: cada petición, su código HTTP, su tiempo y sus aserciones
(`pm.test(...)`). `parse_newman()` convierte **cada aserción en un caso**:

```python
for execution in run["executions"]:
    for assertion in execution["assertions"]:
        status = "Failed" if assertion.get("error") else "Passed"
        cases.append(_case(f"{request_name} › {assertion['assertion']}", status, response_time, error_message))
```

### Importar JUnit XML (Selenium, pytest, Cypress, Playwright)

JUnit es un formato XML estándar: `<testsuite>` contiene `<testcase>`, y un caso fallido tiene dentro `<failure>` o
`<error>`, uno omitido `<skipped>`. `parse_junit()` recorre el XML con `xml.etree.ElementTree`.

`parse_report()` **detecta el formato** mirando el primer carácter (`{` es JSON, `<` es XML) y da un mensaje útil si
subes la colección de Postman en vez del resultado.

---

## 3.6 Automatización: hilos que trabajan solos

Archivos: `backend/automation.py`, `backend/monitor.py`.

Un **hilo** (*thread*) es código que corre en paralelo al servidor. Hay dos, ambos *daemon* (se cierran con el
servidor):

**`AutoTestScheduler`** — cada 5 minutos ejecuta 21 pruebas contra la propia API usando el cliente de pruebas de
Flask (no abre puertos) y guarda los resultados como ejecuciones.

**`MonitorScheduler`** — se despierta cada 20 segundos ("tick") y decide si hay trabajo:

```python
def _loop(self):
    while not self._stop.wait(self.TICK_SECONDS):      # espera 20 s (o termina si se pide parar)
        if daily_report_due():                          # ¿toca el reporte diario?
            generate_auto_report()
        if dt.datetime.now() < self.next_run_at:        # ¿todavía no toca monitorear?
            continue
        for target in store.monitored_targets():        # analiza cada aplicación marcada
            start_scan(target["url"], SYSTEM_USER, target_id=target["id"], trigger="Monitoreo", wait=True)
        self.next_run_at = ahora + intervalo            # el intervalo se lee de Configuración cada vez
```

¿Por qué un tick corto en vez de dormir 30 minutos? Para que **los cambios de Configuración** (otro intervalo) y el
botón "Monitorear ahora" (`run_now()` pone `next_run_at` en el presente) se apliquen en segundos.

`daily_report_due()` es verdadero si hay hora configurada, ya pasó esa hora hoy y **no se generó hoy**
(`report_last_date`). Así el reporte sale una vez al día aunque el tick corra miles de veces.

---

## 3.7 Reportes PDF y Excel

Archivos: `backend/reports_engine.py`, `backend/scan_report.py`, `backend/testdocs_reports.py`.

**PDF con reportlab:** se arma una lista de bloques (*story*) y la librería los acomoda en páginas:

```python
story = [Paragraph("Reporte de defectos", styles["Title"]),
         Spacer(1, 0.3 * cm),
         Table(filas, colWidths=[...])]
doc.build(story, onFirstPage=footer, onLaterPages=footer)   # footer dibuja "Página N"
```

**Excel con openpyxl:** se crea un libro, se escriben celdas y se da formato:

```python
ws.cell(row=1, column=1, value="Código").font = Font(bold=True, color="FFFFFF")
ws.freeze_panes = "A2"                  # la cabecera queda fija al bajar
ws.auto_filter.ref = "A1:J50"           # filtros en la cabecera
```

**Sin archivos temporales:** los documentos se generan en memoria (`io.BytesIO`) y se envían con
`send_file(buffer, as_attachment=True, download_name="reporte_defectos.pdf")`. En el navegador,
`QA.api.download()` recibe el archivo y lo descarga.

En `testdocs_reports.py` las clases `_Pdf` y `_Xlsx` agrupan lo repetido (título, tabla con colores por estado,
campos clave-valor) para que cada reporte sea corto. Las imágenes de evidencia se validan con Pillow antes de
incrustarlas: una imagen dañada no rompe el PDF (las pruebas encontraron ese caso).

---

## 3.8 Documentación QA

Archivos: `backend/testdocs.py`, `backend/testdocs_api.py`.

### Plan de pruebas

Es un documento con secciones de texto libre (objetivo, alcance, funciones, criterios de aceptación, recursos,
cronograma, riesgos). Lo interesante es el **resumen calculado** (`plan_summary`), que no se escribe a mano:

```
casos ejecutados = casos - "No ejecutado"
% ejecución      = ejecutados / casos
pass rate        = aprobados / ejecutados
cobertura        = requisitos con al menos un caso / requisitos
```

### Casos de prueba y su ejecución

Un caso tiene los campos clásicos (precondiciones, datos de entrada, pasos, esperado, obtenido) y se vincula a uno o
varios requisitos mediante la tabla intermedia `spec_requirements` (relación muchos a muchos).

Al **Ejecutar** (`POST /test-cases/<id>/execute`):

1. Se suben las evidencias elegidas (`POST .../evidence`, multipart).
2. Se guarda el resultado en el caso **y** en el historial `spec_executions` (cada ejecución queda registrada).
3. Si el resultado es **Fallido** y se marcó "Crear el reporte de defecto":
   - Si el caso ya tiene un defecto abierto → se suma una reaparición (no se duplica).
   - Si no → se crea una novedad con origen "Caso de prueba", copiando precondiciones, datos y pasos como pasos
     para reproducir, el esperado y el obtenido.

### Evidencias

Los archivos se guardan en `backend/data/evidencias/` con un **nombre aleatorio** (`uuid4().hex + extensión`) y el
nombre original se guarda en la base. Así dos archivos `captura.png` no se pisan y nadie puede adivinar rutas. Solo
se aceptan extensiones de una lista (imágenes, PDF, video, logs, zip) y máximo 10 MB.

### Matriz de trazabilidad (RTM)

`traceability()` arma una fila por requisito con sus casos y calcula la **cobertura** con estas reglas, en orden:

| Si los casos del requisito… | Cobertura |
|---|---|
| no existen | **Sin cobertura** |
| alguno está Fallido | **Con fallas** |
| alguno está Bloqueado | **Bloqueado** |
| todos están Aprobados u Omitidos (y al menos uno Aprobado) | **Validado** |
| cualquier otro caso (hay sin ejecutar) | **Pendiente** |

También lista los **casos sin requisito** (casos huérfanos): pruebas que no justifican ninguna necesidad del cliente.

### Reporte de defectos

No es una tabla nueva: es una **vista documental de las Novedades**, ordenada por severidad, con el **impacto**
explicado según la severidad (por ejemplo, Crítica = "bloquea una función principal o provoca pérdida de datos").
