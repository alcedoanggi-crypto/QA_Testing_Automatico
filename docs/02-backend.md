# 2. Backend: servidor, seguridad y datos

Archivos: `backend/app.py`, `backend/auth.py`, `backend/logger.py`, `backend/qa_api.py`, `backend/qa_store.py`,
`backend/reports_engine.py`.

## 2.1 Cómo arranca el servidor

Cuando ejecutas `python backend/app.py` pasan tres cosas, en este orden:

```python
app = create_app()                 # 1. arma la aplicación Flask

if __name__ == "__main__":
    start_scheduler(app)           # 2. arranca los hilos automáticos
    app.run(host="127.0.0.1", port=5000)   # 3. empieza a escuchar peticiones
```

**`create_app()`** es una *fábrica*: una función que construye la aplicación y la devuelve. Se usa una fábrica (en vez
de crear la app suelta) para que **las pruebas puedan crear su propia app** con una base de datos temporal:

```python
def create_app() -> Flask:
    app = Flask(__name__, template_folder=..., static_folder=...)
    app.extensions["qa_scheduler"] = None   # se llenan en start_scheduler()
    app.extensions["qa_monitor"] = None
    app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024   # tope para archivos subidos
    app.register_blueprint(qa_api)      # rutas de pruebas y seguimiento
    app.register_blueprint(docs_api)    # rutas de documentación QA
    ...
    return app
```

**`start_scheduler()`** marca como "Error" los análisis que quedaron "En curso" si el servidor se apagó a la mitad, y
arranca dos hilos en segundo plano: las autopruebas (cada 5 min) y el monitoreo de aplicaciones (capítulo 3.6).

## 2.2 Rutas y blueprints

Una **ruta** une una URL y un método HTTP con una función de Python:

```python
@api.get("/developers")          # GET /api/v1/developers
@token_required                  # exige estar autenticado
def list_developers():
    return jsonify(store.list_developers())
```

Un **blueprint** es un grupo de rutas con un prefijo común. Hay dos: `qa_api` (en `qa_api.py`) y `docs_api` (en
`testdocs_api.py`), ambos con prefijo `/api/v1`. Así `app.py` no crece sin control.

Las rutas siguen la convención **REST**, que es la misma que usas en Postman:

| Acción | Método | URL | Respuesta |
|---|---|---|---|
| Listar | `GET` | `/api/v1/incidents` | `200` + lista |
| Crear | `POST` | `/api/v1/incidents` | `201` + lo creado |
| Ver uno | `GET` | `/api/v1/incidents/5` | `200` o `404` |
| Editar | `PUT` | `/api/v1/incidents/5` | `200` + lo editado |
| Eliminar | `DELETE` | `/api/v1/incidents/5` | `200` o `404` |

### Manejo de errores en un solo lugar

En vez de escribir `try/except` en cada ruta, la capa de datos **lanza excepciones** y el blueprint las traduce a
respuestas HTTP:

```python
@api.errorhandler(ValueError)        # dato inválido  → 400
def handle_value_error(exc):
    return jsonify({"error": str(exc)}), 400

@api.errorhandler(NotFoundError)     # no existe      → 404
def handle_not_found(exc):
    return jsonify({"error": str(exc)}), 404
```

Por eso una ruta puede ser tan corta como `return jsonify(store.update_developer(dev_id, body()))`: si el correo es
inválido, `update_developer` lanza `ValueError("Correo electrónico inválido")` y el usuario recibe un 400 con ese
mensaje, que la pantalla muestra en rojo.

## 2.3 Seguridad: login y JWT (`auth.py`)

### Contraseñas

Las contraseñas **nunca** se guardan en texto. Se guarda un *hash* (una huella irreversible):

```python
"password_hash": generate_password_hash("SecurePassword123")
...
check_password_hash(user["password_hash"], password)   # True o False
```

### El token JWT

Al iniciar sesión bien, el servidor crea un **JWT**: un texto con tres partes separadas por puntos
(`cabecera.datos.firma`). Los datos dicen quién eres y cuándo vence; la firma se calcula con una clave secreta que solo
conoce el servidor:

```python
payload = {"sub": email, "name": user["name"], "role": user["role"],
           "iat": ahora, "exp": ahora + 60 minutos}
token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

El navegador guarda el token en `localStorage` y lo envía en cada petición:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### El decorador `@token_required`

Un *decorador* envuelve una función para ejecutar algo antes. Este revisa el token antes de cada ruta protegida:

```python
def token_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return jsonify({"error": "Token de autenticación requerido"}), 401
        try:
            g.current_user = decode_token(token.strip())   # valida firma y vencimiento
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "El token ha expirado"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Token inválido"}), 401
        return view(*args, **kwargs)                       # todo bien: ejecuta la ruta
    return wrapper
```

`g.current_user` queda disponible durante la petición; por eso las novedades guardan "Reportado por: Admin QA".

**Para pensar como QA:** las autopruebas del sistema (`automation.py`) prueban justamente estos casos: sin token,
token con firma falsa, token vencido y esquema distinto a `Bearer`. Todos deben dar 401.

## 2.4 Validación de datos

Regla: **nunca confíes en lo que llega del navegador**. Aunque el formulario tenga `maxlength`, alguien puede llamar
a la API directo con Postman. Por eso toda la validación está en el servidor, con funciones pequeñas reutilizables
(`qa_store.py`):

```python
def clean_text(data, key, label, max_len, required=False):
    value = str((data or {}).get(key) or "").strip()
    if required and not value:
        raise ValueError(f"El campo '{label}' es obligatorio")
    if len(value) > max_len:
        raise ValueError(f"El campo '{label}' admite máximo {max_len} caracteres")
    return value

def clean_choice(data, key, label, choices, default):
    value = str((data or {}).get(key) or default).strip()
    if value not in choices:                 # solo valores de una lista cerrada
        raise ValueError(f"{label} inválido. Use: {', '.join(choices)}")
    return value
```

La validación de URL (`clean_url`) merece atención porque las pruebas encontraron un error real en ella:

```python
def clean_url(value, required=True):
    url = str(value or "").strip()
    if re.search(r"\s", url):                      # sin espacios
        raise invalid
    if "://" not in url:
        # "localhost:3000" es válido; "javascript:..." o "mailto:..." no.
        if re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", url, re.IGNORECASE):
            raise invalid
        url = "http://" + url                      # completa el esquema
    parts = urlsplit(url)
    parts.port                                     # lanza error si el puerto no es numérico
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise invalid
    return url
```

La primera versión agregaba `http://` a cualquier cosa sin `://`, así que `javascript:alert(1)` se volvía
`http://javascript:alert(1)` y pasaba. La prueba `test_scan_endpoint_validates_input` lo detectó.
*Lección: escribe pruebas con datos maliciosos, no solo con datos correctos.*

## 2.5 La capa de datos con SQLite

### Conexión segura con `contextmanager`

Cada operación abre una conexión, hace su trabajo, confirma (`commit`) y cierra, **aunque ocurra un error**:

```python
@contextmanager
def _connection(self):
    conn = sqlite3.connect(self.db_path, timeout=10)
    conn.row_factory = sqlite3.Row      # las filas se leen como diccionarios: row["title"]
    try:
        yield conn                      # aquí se ejecuta el bloque "with"
        conn.commit()
    finally:
        conn.close()
```

Uso: `with self._lock, self._connection() as conn: conn.execute(...)`.

`self._lock` es un candado (`threading.Lock`): como hay hilos en segundo plano escribiendo a la vez que el usuario,
el candado evita que dos escrituras se pisen.

### Consultas parametrizadas (protección contra inyección SQL)

Los valores **nunca** se pegan dentro del texto SQL; se pasan aparte con `?`:

```python
# Correcto: SQLite trata el valor como dato, nunca como código
conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))

# Incorrecto (nunca hacer): f"SELECT * FROM incidents WHERE id = {incident_id}"
```

### Códigos legibles (NOV-0001, CP-0001, RUN-1001)

La base genera un `id` numérico; después se calcula un código amigable y se guarda:

```python
cur = conn.execute("INSERT INTO incidents (...) VALUES (...)", valores)
conn.execute("UPDATE incidents SET code = ? WHERE id = ?", (f"NOV-{cur.lastrowid:04d}", cur.lastrowid))
```

### Migración: agregar columnas sin perder datos

La tabla `test_runs` ya existía. Para agregarle columnas nuevas sin borrar la base, al arrancar se compara lo que hay
con lo que se necesita (`reports_engine.py`):

```python
EXTRA_COLUMNS = {"tool": "TEXT NOT NULL DEFAULT ''", "module": "...", "url": "...",
                 "notes": "...", "evidence_url": "...", "updated_at": "TEXT"}

existing = {row["name"] for row in conn.execute("PRAGMA table_info(test_runs)")}
for column, ddl in EXTRA_COLUMNS.items():
    if column not in existing:
        conn.execute(f'ALTER TABLE test_runs ADD COLUMN "{column}" {ddl}')
```

`PRAGMA table_info` devuelve las columnas actuales de la tabla. Si ya están, no hace nada; por eso es seguro
ejecutarlo en cada arranque.

### Eliminar sin dejar datos huérfanos

Cuando se elimina algo que otros registros usan, se decide qué hacer con ellos. Ejemplo, al eliminar un programador
sus novedades **no se borran**, quedan "Sin asignar":

```python
conn.execute("UPDATE incidents SET developer_id = NULL WHERE developer_id = ?", (dev_id,))
conn.execute("UPDATE targets   SET developer_id = NULL WHERE developer_id = ?", (dev_id,))
conn.execute("DELETE FROM developers WHERE id = ?", (dev_id,))
```

## 2.6 Logs

`logger.py` imprime eventos con un formato fijo, fácil de buscar y de probar:

```
[WARNING] [2026-10-19 09:00:00] INTENTO_FALLIDO_LOGIN - Email: admin@test.com | IP: 127.0.0.1
[INFO] [2026-10-19 10:20:02] ANALISIS_URL_INICIADO - SCAN-1001 | http://localhost:3000 | Por: Admin QA
[WARNING] [2026-10-19 10:20:12] NOVEDADES_AUTOMATICAS - SCAN-1001 | Nuevas: 7 | Repetidas: 0
```

Cada evento importante tiene un nombre en MAYÚSCULAS (`CASO_EJECUTADO`, `REPORTE_AUTOMATICO_GENERADO`,
`NOVEDAD_ELIMINADA`…). La prueba `tests/test_console_logs.py` verifica el formato con una expresión regular.

## 2.7 Configuración guardada en la base

La pantalla Configuración guarda pares clave/valor en la tabla `settings`. `get_settings()` mezcla los valores por
defecto con los guardados, y **oculta la contraseña SMTP** al enviarla al navegador:

```python
values = dict(DEFAULT_SETTINGS)
values.update({r["key"]: r["value"] for r in self._all("SELECT key, value FROM settings")})
if not include_secrets:
    for key in SECRET_SETTINGS:                 # {"smtp_password"}
        values[key + "_set"] = bool(values.get(key))   # el navegador solo sabe si existe
        values[key] = ""
```

Al guardar, una contraseña vacía significa "no cambiar la guardada". Así nunca viaja de vuelta al navegador.
