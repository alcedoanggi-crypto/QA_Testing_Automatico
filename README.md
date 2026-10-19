# QA Center

Aplicación web (Flask + JavaScript sin frameworks) para el trabajo diario de QA:

- **Analizar URL**: escribes la URL de tu aplicación (por ejemplo `http://localhost:3000`) y QA Center la abre en
  Chrome sin interfaz y captura **los errores de la consola** (`console.error`, `console.warn`), excepciones de
  JavaScript, promesas rechazadas y peticiones que fallan (404, 500, sin conexión). Puede recorrer varias páginas,
  guarda una captura de pantalla y genera el reporte en PDF o Excel.
- **Resultados Postman / Selenium**: formulario para registrar, editar y eliminar los resultados de las pruebas que
  haces aparte, o importar el archivo de resultados (JSON de Newman o XML JUnit de Selenium, pytest, Cypress o
  Playwright).
- **Novedades**: los errores pasan a los programadores. Se asignan, se envían por correo (SMTP), por webhook (Slack,
  Teams, Discord), con tu propio correo o copiando el texto, y tienen historial y comentarios.
- **Documentación QA**: Plan de pruebas, Casos de prueba (con evidencias adjuntas), Matriz de trazabilidad (RTM) y
  Reporte de defectos, cada uno con su menú, su CRUD y su exportación a PDF y Excel.
- **Automático**: monitoreo periódico de las aplicaciones registradas, creación de novedades sin duplicados, envío al
  programador responsable y reporte diario (PDF + Excel) guardado en el servidor y enviado por correo.

## Acceso, guía y video

| | |
|---|---|
| Carpeta del proyecto | `C:\Users\Pc\Downloads\qa-center` |
| Dirección | http://127.0.0.1:5000 |
| Usuario | `admin@test.com` |
| Contraseña | `SecurePassword123` |
| Guía de aprendizaje (cómo se construyó y su lógica) | [`docs/README.md`](docs/README.md) |
| Video paso a paso (2 min 30 s) | [`docs/video/qa-center-paso-a-paso.mp4`](docs/video/qa-center-paso-a-paso.mp4) |

El video se regenera solo con `pip install imageio imageio-ffmpeg` y `python docs/video/grabar_video.py`
(usa una base de datos temporal; no toca tus datos).

## Instalación (Python 3.10+ y Google Chrome)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/macOS: source .venv/bin/activate
pip install -r backend/requirements.txt
```

## Ejecutar

```bash
python backend/app.py
```

Abrir http://127.0.0.1:5000 — credenciales: `admin@test.com` / `SecurePassword123`.

> Si el panel muestra «Failed to fetch» o «No se pudo conectar con el servidor», el servidor no está en ejecución:
> vuelve a correr `python backend/app.py`.

Variables de entorno opcionales: `PORT`, `HOST`, `JWT_SECRET_KEY`, `JWT_TTL_MINUTES`, `FLASK_DEBUG=1`,
`QA_AUTO_RUN_MINUTES` (autopruebas del sistema, por defecto `5`; `0` las desactiva), `QA_MONITOR=0` (desactiva el
monitoreo y el reporte diario), `QA_DB_PATH` (base SQLite, por defecto `backend/data/qa_reports.db`),
`QA_CHROME_BINARY` y `QA_CHROMEDRIVER` (rutas si Chrome o su driver no se detectan solos).

Los datos se guardan en `backend/data/`: la base SQLite, `screenshots/` (capturas de los análisis),
`evidencias/` (archivos de los casos de prueba) y `reportes/` (reportes automáticos).

## Menús

| Grupo | Menú | Qué hace |
|---|---|---|
| | Resumen | Métricas de pruebas, novedades, análisis de URL y avance de la documentación QA |
| Pruebas | Analizar URL | Errores de consola, JavaScript y red de cualquier URL (localhost incluido) |
| | Resultados Postman / Selenium | Registrar, editar, eliminar e importar resultados externos |
| | Pruebas automáticas | QA Center se prueba a sí mismo cada 5 minutos |
| Documentación QA | Plan de pruebas | Alcance, funciones a evaluar, criterios de aceptación, recursos, cronograma, riesgos |
| | Casos de prueba | ID, precondiciones, datos de entrada, pasos, esperado vs. obtenido, evidencias; ejecución con defecto automático |
| | Matriz de trazabilidad | Requisitos / historias de usuario ↔ casos de prueba, cobertura y defectos |
| | Reporte de defectos | Documento para desarrollo con pasos de reproducción e impacto por severidad |
| Seguimiento | Novedades | Gestión de defectos: asignar, enviar, cambiar estado, comentar, acciones masivas |
| | Programadores | Equipo que recibe las novedades |
| | Aplicaciones | URLs a monitorear automáticamente y su responsable |
| Sistema | Reportes | Informe ejecutivo, novedades, documentación QA y reportes automáticos |
| | Configuración | Monitoreo, novedades automáticas, webhook, correo SMTP y reporte diario |

## Flujo recomendado

1. Registra a los **programadores** y las **aplicaciones** (URL + responsable; marca «Monitorear»).
2. Crea el **plan de pruebas** y carga los **requisitos / historias** en la matriz de trazabilidad.
3. Escribe los **casos de prueba** y vincúlalos a los requisitos.
4. **Ejecuta** cada caso: si falla, se crea el defecto (novedad) con los pasos, el resultado obtenido y las evidencias.
5. Usa **Analizar URL** para detectar errores de consola; los errores se convierten en novedades automáticamente.
6. Registra o importa tus pruebas de **Postman / Selenium**.
7. Envía las **novedades** a los programadores y descarga los **reportes**.

## API REST (principal)

Todas las rutas (salvo login y health) requieren `Authorization: Bearer <token>`.

| Recurso | Endpoints |
|---|---|
| Autenticación | `POST /api/v1/auth/login` |
| Métricas | `GET /api/v1/dashboard/metrics` |
| Análisis de URL | `POST/GET /api/v1/scans`, `GET/DELETE /api/v1/scans/<id>`, `GET /api/v1/scans/<id>/report?format=pdf\|excel`, `POST /api/v1/scans/<id>/incidents` |
| Resultados | `GET/POST /api/v1/test-runs`, `GET/PUT/DELETE /api/v1/test-runs/<id>`, `POST /api/v1/test-runs/import`, `POST /api/v1/test-runs/<id>/incidents` |
| Planes | `GET/POST /api/v1/plans`, `GET/PUT/DELETE /api/v1/plans/<id>`, `GET /api/v1/plans/<id>/report` |
| Requisitos | `GET/POST /api/v1/requirements`, `PUT/DELETE /api/v1/requirements/<id>` |
| Casos de prueba | `GET/POST /api/v1/test-cases`, `GET/PUT/DELETE /api/v1/test-cases/<id>`, `POST .../execute`, `POST .../evidence`, `POST .../duplicate`, `GET /api/v1/test-cases/report` |
| Trazabilidad | `GET /api/v1/rtm`, `GET /api/v1/rtm/report` |
| Defectos / novedades | `GET/POST /api/v1/incidents`, `GET/PUT/DELETE /api/v1/incidents/<id>`, `POST .../comments`, `POST .../notify`, `POST /api/v1/incidents/bulk`, `GET /api/v1/defects/report`, `GET /api/v1/incidents/<id>/report` |
| Programadores / aplicaciones | `GET/POST /api/v1/developers`, `PUT/DELETE /api/v1/developers/<id>`, igual para `/api/v1/targets` |
| Reportes | `GET /api/v1/reports/export?format=pdf\|excel\|csv`, `GET/POST /api/v1/reports/auto`, `GET/DELETE /api/v1/reports/auto/<archivo>` |
| Configuración | `GET/PUT /api/v1/settings`, `POST /api/v1/settings/test-webhook`, `POST /api/v1/settings/test-email` |

## Pruebas

```bash
python -m pytest tests/ -v                       # todo (requiere Google Chrome para la parte E2E)
python -m pytest tests/test_qa_center.py -v      # análisis, resultados, novedades, reportes, configuración
python -m pytest tests/test_testdocs.py -v       # plan, casos, evidencias, trazabilidad, defectos
python -m pytest tests/test_selenium_ui.py -v -s # E2E con Selenium (HEADLESS=0 para ver el navegador)
```

Las pruebas usan una base SQLite temporal; no tocan `backend/data/`.
