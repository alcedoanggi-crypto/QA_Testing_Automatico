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
| Video: cómo probar otra aplicación (2 min 15 s) | [`docs/video/qa-center-probar-otra-aplicacion.mp4`](docs/video/qa-center-probar-otra-aplicacion.mp4) |

El video se regenera solo con `pip install imageio imageio-ffmpeg` y `python docs/video/grabar_video.py`
(usa una base de datos temporal; no toca tus datos).

## Reportes de las pruebas

### Resultado de las pruebas automatizadas

**54 pruebas · 54 exitosas · 0 fallidas** (API, lógica y navegador real con Selenium).
Detalle de cada prueba: [`docs/reportes/pruebas/resultado-pruebas.md`](docs/reportes/pruebas/resultado-pruebas.md) ·
archivo JUnit: [`junit.xml`](docs/reportes/pruebas/junit.xml).

![Resultado de las pruebas automatizadas](docs/reportes/pruebas/resultado-pruebas.png)

### Reportes que genera QA Center

Primera página de cada reporte, generado con datos de demostración. Haz clic en la imagen para verla en grande o
descarga el PDF y el Excel completos.

<table>
<tr><td width="50%" valign="top"><b>Informe ejecutivo de pruebas</b><br><a href="docs/reportes/ejemplos/01-informe-ejecutivo.pdf">PDF</a> · <a href="docs/reportes/ejemplos/01-informe-ejecutivo.xlsx">Excel</a><br><a href="docs/reportes/vistas/01-informe-ejecutivo.png"><img src="docs/reportes/vistas/01-informe-ejecutivo.png" alt="Informe ejecutivo de pruebas" width="100%"></a></td><td width="50%" valign="top"><b>Plan de pruebas</b><br><a href="docs/reportes/ejemplos/02-plan-de-pruebas.pdf">PDF</a> · <a href="docs/reportes/ejemplos/02-plan-de-pruebas.xlsx">Excel</a><br><a href="docs/reportes/vistas/02-plan-de-pruebas.png"><img src="docs/reportes/vistas/02-plan-de-pruebas.png" alt="Plan de pruebas" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Casos de prueba</b><br><a href="docs/reportes/ejemplos/03-casos-de-prueba.pdf">PDF</a> · <a href="docs/reportes/ejemplos/03-casos-de-prueba.xlsx">Excel</a><br><a href="docs/reportes/vistas/03-casos-de-prueba.png"><img src="docs/reportes/vistas/03-casos-de-prueba.png" alt="Casos de prueba" width="100%"></a></td><td width="50%" valign="top"><b>Matriz de trazabilidad</b><br><a href="docs/reportes/ejemplos/04-matriz-trazabilidad.pdf">PDF</a> · <a href="docs/reportes/ejemplos/04-matriz-trazabilidad.xlsx">Excel</a><br><a href="docs/reportes/vistas/04-matriz-trazabilidad.png"><img src="docs/reportes/vistas/04-matriz-trazabilidad.png" alt="Matriz de trazabilidad" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Reporte de defectos</b><br><a href="docs/reportes/ejemplos/05-reporte-defectos.pdf">PDF</a> · <a href="docs/reportes/ejemplos/05-reporte-defectos.xlsx">Excel</a><br><a href="docs/reportes/vistas/05-reporte-defectos.png"><img src="docs/reportes/vistas/05-reporte-defectos.png" alt="Reporte de defectos" width="100%"></a></td><td width="50%" valign="top"><b>Análisis de URL (errores de consola)</b><br><a href="docs/reportes/ejemplos/06-analisis-url.pdf">PDF</a> · <a href="docs/reportes/ejemplos/06-analisis-url.xlsx">Excel</a><br><a href="docs/reportes/vistas/06-analisis-url.png"><img src="docs/reportes/vistas/06-analisis-url.png" alt="Análisis de URL (errores de consola)" width="100%"></a></td></tr>
</table>

## Capturas de todo el sistema

<table>
<tr><td width="50%" valign="top"><b>Inicio de sesión</b><br><a href="docs/capturas/00-login.png"><img src="docs/capturas/00-login.png" alt="Inicio de sesión" width="100%"></a></td><td width="50%" valign="top"><b>Resumen</b><br><a href="docs/capturas/01-resumen.png"><img src="docs/capturas/01-resumen.png" alt="Resumen" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Analizar URL: errores de consola, JavaScript y red</b><br><a href="docs/capturas/02-analizar-url.png"><img src="docs/capturas/02-analizar-url.png" alt="Analizar URL: errores de consola, JavaScript y red" width="100%"></a></td><td width="50%" valign="top"><b>Resultados de Postman / Selenium</b><br><a href="docs/capturas/03-resultados-postman-selenium.png"><img src="docs/capturas/03-resultados-postman-selenium.png" alt="Resultados de Postman / Selenium" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Pruebas automáticas del sistema</b><br><a href="docs/capturas/04-pruebas-automaticas.png"><img src="docs/capturas/04-pruebas-automaticas.png" alt="Pruebas automáticas del sistema" width="100%"></a></td><td width="50%" valign="top"><b>Plan de pruebas</b><br><a href="docs/capturas/05-plan-de-pruebas.png"><img src="docs/capturas/05-plan-de-pruebas.png" alt="Plan de pruebas" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Plan de pruebas: formulario</b><br><a href="docs/capturas/06-plan-formulario.png"><img src="docs/capturas/06-plan-formulario.png" alt="Plan de pruebas: formulario" width="100%"></a></td><td width="50%" valign="top"><b>Casos de prueba</b><br><a href="docs/capturas/07-casos-de-prueba.png"><img src="docs/capturas/07-casos-de-prueba.png" alt="Casos de prueba" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Caso de prueba: formulario</b><br><a href="docs/capturas/08-caso-formulario.png"><img src="docs/capturas/08-caso-formulario.png" alt="Caso de prueba: formulario" width="100%"></a></td><td width="50%" valign="top"><b>Caso de prueba: ejecutar y crear defecto</b><br><a href="docs/capturas/09-caso-ejecutar.png"><img src="docs/capturas/09-caso-ejecutar.png" alt="Caso de prueba: ejecutar y crear defecto" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Caso de prueba: detalle, evidencias e historial</b><br><a href="docs/capturas/10-caso-detalle.png"><img src="docs/capturas/10-caso-detalle.png" alt="Caso de prueba: detalle, evidencias e historial" width="100%"></a></td><td width="50%" valign="top"><b>Matriz de trazabilidad (RTM)</b><br><a href="docs/capturas/11-matriz-trazabilidad.png"><img src="docs/capturas/11-matriz-trazabilidad.png" alt="Matriz de trazabilidad (RTM)" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Reporte de defectos</b><br><a href="docs/capturas/12-reporte-defectos.png"><img src="docs/capturas/12-reporte-defectos.png" alt="Reporte de defectos" width="100%"></a></td><td width="50%" valign="top"><b>Novedades</b><br><a href="docs/capturas/13-novedades.png"><img src="docs/capturas/13-novedades.png" alt="Novedades" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Novedad: detalle y envío al programador</b><br><a href="docs/capturas/14-novedad-detalle.png"><img src="docs/capturas/14-novedad-detalle.png" alt="Novedad: detalle y envío al programador" width="100%"></a></td><td width="50%" valign="top"><b>Programadores</b><br><a href="docs/capturas/15-programadores.png"><img src="docs/capturas/15-programadores.png" alt="Programadores" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Aplicaciones monitoreadas</b><br><a href="docs/capturas/16-aplicaciones.png"><img src="docs/capturas/16-aplicaciones.png" alt="Aplicaciones monitoreadas" width="100%"></a></td><td width="50%" valign="top"><b>Reportes</b><br><a href="docs/capturas/17-reportes.png"><img src="docs/capturas/17-reportes.png" alt="Reportes" width="100%"></a></td></tr>
<tr><td width="50%" valign="top"><b>Configuración</b><br><a href="docs/capturas/18-configuracion.png"><img src="docs/capturas/18-configuracion.png" alt="Configuración" width="100%"></a></td></tr>
</table>

Para regenerar los resultados, los reportes y las capturas: `pip install pypdfium2` y
`python docs/reportes/generar_reportes.py` (usa bases de datos temporales; no toca tus datos).

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
