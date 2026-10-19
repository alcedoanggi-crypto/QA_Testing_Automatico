# 6. Pruebas automatizadas

Archivos: `tests/`. Total: **54 pruebas**.

```bash
python -m pytest tests/ -v
```

## 6.1 La pirámide de pruebas del proyecto

```
                 ▲   test_selenium_ui.py   (11)  navegador real: hace clic como un usuario
                ▲▲▲  test_qa_center.py     (21)  API: análisis, resultados, novedades, reportes
               ▲▲▲▲▲ test_testdocs.py      (7)   API: plan, casos, evidencias, trazabilidad
              ▲▲▲▲▲▲ test_system_runner.py (9)   autopruebas y programador
             ▲▲▲▲▲▲▲ test_console_logs.py  (6)   formato de los logs
```

Abajo hay muchas pruebas rápidas (milisegundos); arriba pocas pruebas lentas (segundos) pero que prueban todo junto.

## 6.2 Cada prueba usa su propia base de datos

Ninguna prueba toca tus datos reales. Al inicio de cada archivo:

```python
os.environ.setdefault("QA_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="qa_center_test_"), "qa_reports.db"))
```

Como la ruta de la base se lee de una variable de entorno, basta con cambiarla **antes** de importar la aplicación.

## 6.3 Pruebas de API con el cliente de Flask

El cliente de pruebas hace peticiones a la aplicación **sin levantar un servidor**: es como Postman, pero desde Python
y muchísimo más rápido.

```python
class QACenterTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        token = cls.app.test_client().post("/api/v1/auth/login",
                    json={"email": "admin@test.com", "password": "SecurePassword123"}).get_json()["token"]
        cls.headers = {"Authorization": f"Bearer {token}"}

    def test_developer_crud(self):
        dev = self.call("post", "/developers", 201, json={"name": "Ana", "email": "ana@empresa.com"})
        self.call("post", "/developers", 400, json={"name": "Otra", "email": "ana@empresa.com"})   # duplicado
        self.call("delete", f"/developers/{dev['id']}")
        self.call("delete", f"/developers/{dev['id']}", 404)                                      # ya no existe
```

`self.call()` es un ayudante que hace la petición y verifica el código HTTP esperado. Fíjate en el estilo: cada
prueba verifica el **camino feliz** y también los **errores** (duplicado, dato inválido, no existe).

## 6.4 Reemplazar una pieza lenta (*mock*)

Para probar la lógica de novedades no hace falta abrir Chrome: se reemplaza el analizador por uno falso que devuelve
errores conocidos.

```python
def fake_scan(issues):
    def _scan(url, max_pages=1, wait_seconds=2.0, screenshot_path=None):
        return {"engine": "Falso", "http_status": 200, "pages_scanned": 1, "message": "",
                "issues": [dict(i, page_url=url) for i in issues]}
    return _scan

monitor.scan_url = fake_scan([{"level": "error", "source": "javascript", "message": "TypeError ... app.js:10:5"}])
scan = monitor.start_scan(url, "Tester", auto_incidents=True, wait=True)
```

Así `test_scan_creates_incidents_without_duplicates` comprueba en milisegundos que:
- solo los errores (no las advertencias) crean novedades,
- se asignan al responsable de la aplicación,
- el mismo error con otro número de línea **no** crea otra novedad, sino que suma una reaparición.

`tearDown` devuelve el analizador real a su lugar para no afectar otras pruebas.

## 6.5 Un servidor falso para probar el webhook

Para verificar que el mensaje realmente sale hacia Slack/Teams, la prueba levanta un mini servidor HTTP local que
guarda lo que recibe, y apunta el webhook a él:

```python
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200); self.end_headers()

server = HTTPServer(("127.0.0.1", 0), Handler)      # puerto 0 = el sistema elige uno libre
...
self.assertIn("Error 500 en pagos", received[-1]["text"])
```

## 6.6 Pruebas de punta a punta con Selenium

`test_selenium_ui.py` levanta la aplicación real en un hilo y la maneja con Chrome:

```python
def open_view(self, name):
    self.driver.find_element(By.CSS_SELECTOR, f"a[data-nav='{name}']").click()
    return self.wait.until(EC.visibility_of_element_located((By.ID, f"view-{name}")))
```

Buenas prácticas que aplica:

- **Esperas explícitas** (`WebDriverWait(...).until(...)`) en lugar de `time.sleep`: espera lo justo.
- **Selectores por `id`** estables (`#btn-run-tests`, `#run-suite`), no por texto ni posición.
- **Tolerar elementos que se redibujan**: las tablas se vuelven a pintar al recargar datos, lo que produce
  `StaleElementReferenceException`. La espera se configura para reintentar:
  `WebDriverWait(driver, 15, ignored_exceptions=(StaleElementReferenceException,))`.
- **Cada prueba parte limpia**: `setUp` borra el `localStorage` (sin sesión).

Pruebas destacadas:

| Prueba | Qué recorre |
|---|---|
| `test_08_scan_url_detects_console_errors` | Levanta una página rota, la analiza desde la pantalla y verifica que aparezcan el `console.error`, el `ReferenceError`, el 404 y las novedades creadas |
| `test_10_test_documentation_flow` | Plan → requisito → caso → ejecución fallida con evidencia → defecto → matriz "Con fallas" → reporte de defectos |
| `test_11_all_menus_without_console_errors` | Recorre los 13 menús y exige **cero errores en la consola** de QA Center |

La prueba 11 aplica a QA Center la misma idea que el analizador aplica a tus aplicaciones: para leer la consola se
activa `goog:loggingPrefs` y se lee `driver.get_log("browser")`.

## 6.7 Errores reales que encontraron las pruebas

| Prueba | Error encontrado | Corrección |
|---|---|---|
| validación de URL | `javascript:alert(1)` y URLs con espacios eran aceptadas | `clean_url` más estricta (capítulo 2.4) |
| evidencias | Una imagen dañada hacía fallar el PDF con error 500 | Se valida la imagen con Pillow antes de incrustarla |
| evidencias | En Windows no se podía borrar una evidencia recién descargada (archivo bloqueado) | Se sirve el archivo desde memoria |
| Selenium | Leer una tarjeta de una vista oculta devuelve texto vacío | Navegar a la vista antes de leer |

## 6.8 Postman

`tests/postman_collection.json` es una colección para probar la API a mano o con Newman:

```bash
newman run tests/postman_collection.json -r json --reporter-json-export resultado.json
```

Y ese `resultado.json` lo puedes **importar en QA Center** (menú Resultados) para cerrar el ciclo.
