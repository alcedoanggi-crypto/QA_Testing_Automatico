# 7. Práctica: recorridos, cambios y ejercicios

## 7.1 Acceso a la aplicación

| Dato | Valor |
|---|---|
| Carpeta del proyecto | `C:\Users\Pc\Downloads\qa-center` |
| Dirección | http://127.0.0.1:5000 |
| Usuario (correo) | `admin@test.com` |
| Contraseña | `SecurePassword123` |
| Nombre y rol | Admin QA · Lead QA |

El usuario está definido en `backend/auth.py`, en el diccionario `USERS`. Para **agregar otro usuario**:

```python
USERS = {
    "admin@test.com": {"name": "Admin QA", "role": "Lead QA",
                       "password_hash": generate_password_hash("SecurePassword123")},
    "anggie@empresa.com": {"name": "Anggie Alcedo", "role": "QA Analyst",
                           "password_hash": generate_password_hash("UnaClaveSegura2026")},
}
```

Reinicia el servidor y ya puedes entrar con el nuevo correo. (Para producción, los usuarios deberían ir en la base de
datos; dejarlos en código es una simplificación para aprender.)

Por comodidad, la pantalla de login trae los datos de prueba precargados. Para quitarlos: `set QA_DEMO_LOGIN=0`
antes de `python backend/app.py`.

## 7.2 Recorrido de una petición de punta a punta

Sigamos qué pasa cuando, en **Casos de prueba**, marcas un caso como **Fallido** y pulsas **Registrar resultado**.

```
1. docs.js · saveExecution()
   - lee el resultado elegido (radio "Fallido") y el texto "Resultado obtenido"
   - si hay archivos, primero los sube:  POST /api/v1/test-cases/7/evidence   (FormData)
   - luego:                              POST /api/v1/test-cases/7/execute
        {"status":"Fallido","actual":"Error 500","create_defect":true,"severity":"Alta","developer_id":2}

2. core.js · request()  agrega  Authorization: Bearer <token>  y envía el JSON

3. auth.py · @token_required  valida el token → g.current_user = {"name": "Admin QA", ...}

4. testdocs_api.py · execute_spec(7)
   - docs.get_spec(7)                          ← lee el caso
   - ¿tiene defecto abierto?  no →  store.create_incident({...pasos, esperado, obtenido...},
                                                          source="Caso de prueba", source_ref="CP-0007")
                                                          → INSERT en incidents  → NOV-0012
                                                          → INSERT en incident_history ("Creación")
   - docs.record_execution(7, datos, "Admin QA", incident_id=12)
                                                          → UPDATE test_specs  (estado, obtenido, fecha)
                                                          → INSERT spec_executions (historial)
   - log: [INFO] CASO_EJECUTADO - CP-0007 | Resultado: Fallido | Defecto: NOV-0012
   - responde 200 {caso actualizado, "defect": {...NOV-0012...}}

5. docs.js  cierra el diálogo, muestra el aviso "CP-0007: Fallido · defecto NOV-0012 enviado a Novedades"
   y emite eventos:  docs-changed · incidents-changed · data-changed

6. Cada módulo reacciona a su evento: la tabla de casos se recarga, la matriz de trazabilidad pasa a
   "Con fallas", el contador de Novedades del menú sube y el Resumen actualiza sus tarjetas.
```

**Ejercicio:** hazlo con F12 abierto en la pestaña **Red** y encuentra las peticiones del paso 1. Mira el cuerpo
enviado y la respuesta.

## 7.3 Cómo agregar un campo nuevo (ejemplo: "Navegador" en los casos de prueba)

Se tocan las mismas capas en el mismo orden:

1. **Base de datos** (`testdocs.py`, `SCHEMA`): agrega `browser TEXT NOT NULL DEFAULT ''` a `test_specs`. Como la tabla
   ya existe en tu base, agrega también una migración como la de `reports_engine.py` (capítulo 2.5) o borra
   `backend/data/qa_reports.db` si no te importan los datos.
2. **Validación** (`_validate_spec`): `"browser": clean_choice(data, "browser", "Navegador", ["Chrome", "Firefox", "Edge"], "Chrome")`.
3. **Pantalla** (`dashboard.html`, diálogo `dlg-case`): agrega un `<select id="case-browser">`.
4. **JS** (`docs.js`): agrega `browser: "case-browser"` en `CASE_FIELDS`. Como el formulario se llena y se lee
   recorriendo ese objeto, no hace falta nada más.
5. **Reporte** (`testdocs_reports.py`): agrega la columna en `CASE_HEADERS` y en `_case_row`.
6. **Prueba** (`tests/test_testdocs.py`): crea un caso con `"browser": "Firefox"` y verifica que se guarde; y uno con
   `"browser": "Netscape"` que debe dar 400.

## 7.4 Cómo agregar un menú nuevo

1. En `dashboard.html`: un enlace `<a href="#mimenu" data-nav="mimenu">Mi menú</a>` y una sección
   `<section id="view-mimenu" class="view" data-view="mimenu" hidden>…</section>`.
2. Un archivo `frontend/static/js/mimenu.js` con `QA.on("view:mimenu", cargar)` y agrégalo al final de
   `dashboard.html` con `<script src=...>`.
3. Si necesita datos: tabla en un `*_store`, rutas en un blueprint, pruebas.

El enrutador de `core.js` ya sabe mostrarlo; no hay que cambiarlo.

## 7.5 Ejercicios para practicar

Ordenados de más fácil a más difícil.

1. **Cambiar un color**: en `styles.css` cambia `--primary` y mira cómo cambia toda la aplicación.
2. **Nuevo estado de caso**: agrega "Reprobado por datos" a `CASE_STATUSES` en `testdocs.py`. ¿Qué pantallas lo
   muestran solas? (Pista: los `<select>` se llenan desde `/api/v1/docs/catalogs`.)
3. **Validación**: impide crear un caso de prueba sin "Resultado esperado". Escribe primero la prueba que falla y
   después el código que la hace pasar (esto se llama TDD).
4. **Consulta SQL**: en la sección 5.3 hay consultas; escribe una que liste los casos fallidos con su defecto.
5. **Nuevo canal**: agrega a `notifier.py` el envío a Telegram (API `sendMessage`). Pruébalo con un servidor falso
   como en la sección 6.5.
6. **Nueva fuente de errores en el analizador**: haz que el analizador reporte como advertencia las páginas que
   tardan más de 3 segundos en cargar (`load_ms`).
7. **Prueba Selenium**: escribe una prueba que cree un programador desde la pantalla, lo edite y lo elimine.

## 7.6 Problemas comunes

| Síntoma | Causa | Solución |
|---|---|---|
| "Failed to fetch" / "No se pudo conectar con el servidor" | El servidor no está corriendo | `python backend/app.py` |
| `ModuleNotFoundError: No module named 'flask'` | No activaste el entorno virtual | `.venv\Scripts\activate` |
| El analizador dice "Sin navegador: solo se revisaron respuestas HTTP" | Chrome no está instalado o no se encontró | Instala Chrome o define `QA_CHROME_BINARY` |
| Análisis en "Error": "No se pudo abrir …" | La aplicación a analizar no está encendida o la URL está mal | Abre la URL en tu navegador para comprobarla |
| "Sesión expirada" | El token dura 60 minutos | Vuelve a iniciar sesión (o cambia `JWT_TTL_MINUTES`) |
| El correo no sale | SMTP sin configurar o clave incorrecta (Gmail exige "contraseña de aplicación") | Configuración → Probar correo |
| `Address already in use` | Ya hay otro servidor en el puerto 5000 | Cierra el otro o usa `set PORT=5001` |

## 7.7 Glosario

| Término | Significado |
|---|---|
| API REST | Forma de comunicar programas por HTTP usando URLs y métodos (GET, POST, PUT, DELETE) |
| JSON | Formato de texto para datos: `{"title": "Error", "severity": "Alta"}` |
| JWT | Token firmado que prueba quién eres en cada petición |
| Blueprint | Grupo de rutas de Flask |
| Decorador | Función que envuelve a otra (`@token_required`) |
| Headless | Navegador sin ventana, controlado por código |
| CDP | Chrome DevTools Protocol: la misma interfaz que usa F12, accesible desde Selenium |
| Hilo (thread) | Código que corre en paralelo al servidor |
| Polling | Preguntar cada cierto tiempo si algo terminó |
| Huella (fingerprint) | Resumen que identifica "el mismo error" para no duplicarlo |
| Migración | Cambio a la estructura de la base sin perder datos |
| Mock | Pieza falsa que reemplaza a una real en una prueba |
| SPA | Aplicación de una sola página que cambia de vista sin recargar |
| XSS | Ataque que inyecta código en una página; se evita escapando el texto |
| RTM | Matriz de trazabilidad: requisitos ↔ casos de prueba |
