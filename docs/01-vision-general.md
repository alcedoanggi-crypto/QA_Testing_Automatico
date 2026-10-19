# 1. Visión general y cómo se construyó

## 1.1 Qué problema resuelve

Un equipo de QA necesita, en un solo lugar:

1. **Detectar errores** en la aplicación que prueba (lo que aparece en la consola del navegador).
2. **Registrar resultados** de pruebas hechas con otras herramientas (Postman, Selenium).
3. **Documentar** el trabajo: plan de pruebas, casos de prueba, matriz de trazabilidad.
4. **Pasar los errores a los programadores** y darles seguimiento hasta que se corrijan.
5. **Generar reportes** (PDF y Excel) para el equipo y la gerencia.
6. Que todo lo anterior pueda pasar **solo**, sin que alguien tenga que pulsar un botón.

QA Center es una aplicación web que hace esas seis cosas.

## 1.2 Tecnologías y por qué se eligieron

| Parte | Tecnología | Por qué |
|---|---|---|
| Servidor | **Python + Flask** | Flask es pequeño y fácil de leer: una función por ruta. Ideal para aprender. |
| Base de datos | **SQLite** (módulo `sqlite3` de Python) | Es un solo archivo, no hay que instalar un servidor de base de datos. |
| Seguridad | **JWT** con `PyJWT`, contraseñas con `werkzeug.security` | Estándar de la industria para APIs: el navegador guarda un token firmado. |
| Navegador automático | **Selenium + Chrome sin interfaz (headless)** | Es la forma real de ver los errores de consola: hay que ejecutar la página en un navegador de verdad. |
| Reportes | **reportlab** (PDF) y **openpyxl** (Excel) | Librerías maduras para generar documentos desde Python. |
| Pantalla | **HTML + CSS + JavaScript sin frameworks** | No hay que compilar nada; se ve exactamente lo que se escribe. |
| Pruebas | **unittest/pytest**, cliente de pruebas de Flask y **Selenium** | Las mismas herramientas que usa un QA automatizador. |

## 1.3 Arquitectura

La aplicación tiene tres capas. Cada capa solo habla con la de al lado:

```
┌───────────────────────────────────────────────────────────────────────────┐
│ NAVEGADOR (frontend/)                                                     │
│  dashboard.html  ← una sola página con 13 vistas (menús)                  │
│  core.js         ← llamadas a la API con el token, rutas #vista, diálogos │
│  dashboard.js, scanner.js, results.js, incidents.js, people.js,           │
│  settings.js, docs.js  ← un archivo por grupo de menús                    │
└──────────────▲────────────────────────────────────────────────────────────┘
               │ HTTP + JSON   (Authorization: Bearer <token JWT>)
┌──────────────┴────────────────────────────────────────────────────────────┐
│ SERVIDOR FLASK (backend/)                                                 │
│  app.py            ← crea la aplicación, rutas base y arranca los hilos   │
│  qa_api.py         ← rutas de análisis, resultados, novedades, config.    │
│  testdocs_api.py   ← rutas de plan, casos, trazabilidad, defectos         │
│  auth.py           ← login y protección de rutas con JWT                  │
│                                                                           │
│  LÓGICA:  url_scanner.py (Chrome) · monitor.py (orquesta y automatiza)    │
│           importers.py · notifier.py · automation.py                      │
│  REPORTES: reports_engine.py · scan_report.py · testdocs_reports.py       │
│  DATOS:   reports_engine.py (ejecuciones) · qa_store.py · testdocs.py     │
└──────────────┬────────────────────────────────────────────────────────────┘
               │ SQL
┌──────────────▼────────────────────────────────────────────────────────────┐
│ backend/data/qa_reports.db  (SQLite)  + carpetas screenshots/,           │
│ evidencias/ y reportes/                                                   │
└───────────────────────────────────────────────────────────────────────────┘
```

**Regla de oro de esta arquitectura:** las rutas (`*_api.py`) no escriben SQL; solo reciben la petición, llaman a la
capa de datos o de lógica y devuelven JSON. Así cada archivo tiene una sola responsabilidad y es fácil de probar.

## 1.4 Estructura de carpetas

```
qa-center/
├── backend/
│   ├── app.py               Punto de entrada. create_app() arma Flask; start_scheduler() arranca los hilos.
│   ├── auth.py              Usuarios, hash de contraseña, crear/validar JWT, decorador @token_required.
│   ├── logger.py            Logs con formato [NIVEL] [fecha] EVENTO - detalle.
│   ├── reports_engine.py    Tabla de ejecuciones de pruebas, métricas, reporte ejecutivo PDF/Excel/CSV.
│   ├── automation.py        21 pruebas que la app se hace a sí misma + programador cada 5 min.
│   ├── qa_store.py          Programadores, aplicaciones, análisis, novedades, historial y configuración.
│   ├── url_scanner.py       Abre la URL en Chrome y captura errores de consola, JavaScript y red.
│   ├── monitor.py           Lanza análisis en segundo plano, crea novedades, monitoreo y reporte diario.
│   ├── notifier.py          Arma el mensaje de la novedad y lo envía por correo o webhook.
│   ├── importers.py         Lee resultados de Newman (Postman) y JUnit XML (Selenium, pytest…).
│   ├── scan_report.py       PDF/Excel de un análisis de URL.
│   ├── testdocs.py          Planes, requisitos, casos de prueba, evidencias y matriz de trazabilidad.
│   ├── testdocs_reports.py  PDF/Excel del plan, casos, trazabilidad y defectos.
│   ├── qa_api.py            API REST de los módulos de pruebas y seguimiento.
│   ├── testdocs_api.py      API REST de la documentación QA.
│   └── requirements.txt     Dependencias de Python.
├── frontend/
│   ├── templates/           login.html y dashboard.html (Flask las sirve).
│   └── static/              css/styles.css y los archivos js/.
├── tests/                   Pruebas automatizadas (ver capítulo 6).
├── docs/                    Esta guía.
└── README.md                Instalación y uso.
```

## 1.5 Cómo se construyó (el orden importa)

La aplicación no se escribió de una vez; se fue construyendo por capas, probando cada paso antes de seguir. Este orden
es una buena receta para cualquier proyecto:

**Etapa 1 — Partir de una base que funciona.** Se copió la aplicación *QA Reports* (login con JWT, dashboard de
métricas, exportación PDF/Excel/CSV y autopruebas) a una carpeta nueva e independiente. Antes de cambiar nada se
corrieron sus pruebas (15 pasaban). *Lección: nunca empieces a modificar sin saber que lo que tienes funciona.*

**Etapa 2 — Ampliar el modelo de datos sin romper lo existente.** La tabla de ejecuciones necesitaba nuevos campos
(herramienta, módulo, URL, notas, evidencia). En lugar de borrar la base, se agregó una **migración**: al arrancar, el
código revisa qué columnas faltan y las crea con `ALTER TABLE` (ver capítulo 2.5). Luego se agregaron editar y eliminar.

**Etapa 3 — La capa de datos nueva (`qa_store.py`).** Se diseñaron las tablas de programadores, aplicaciones,
análisis, errores encontrados, novedades, historial y configuración, con funciones `create_`, `get_`, `update_`,
`delete_` y validación de cada campo.

**Etapa 4 — El analizador de URL (`url_scanner.py`).** Es la pieza más técnica. Se probó primero **solo**, sin servidor
ni pantalla, contra una página con errores a propósito (un `console.error`, una función inexistente, un archivo que
no existe). Cuando detectó los 9 errores esperados, se conectó al resto.

**Etapa 5 — Orquestación y notificaciones (`monitor.py`, `notifier.py`, `importers.py`).** Lo que une las piezas:
lanzar el análisis en segundo plano, convertir errores en novedades sin duplicar, enviar correos y webhooks, leer
archivos de Newman y JUnit.

**Etapa 6 — La API (`qa_api.py`).** Una ruta por acción, todas protegidas con JWT.

**Etapa 7 — La pantalla.** Se cambió el panel lateral fijo por un **menú** con vistas, se escribió `core.js` (lo común
a todas las pantallas) y luego un archivo JS por grupo de menús.

**Etapa 8 — Pruebas.** Pruebas de API para cada módulo y pruebas Selenium que hacen clic como un usuario. Las pruebas
encontraron errores reales que se corrigieron (por ejemplo, la URL `javascript:alert(1)` era aceptada).

**Etapa 9 — Reportes y automatización.** Reporte por análisis, novedades y análisis dentro del informe ejecutivo,
reporte diario automático.

**Etapa 10 — Documentación QA.** Plan de pruebas, casos de prueba con evidencias, matriz de trazabilidad y reporte de
defectos: otra capa de datos (`testdocs.py`), su API (`testdocs_api.py`), sus documentos (`testdocs_reports.py`) y su
pantalla (`docs.js`).

**Etapa 11 — Revisión visual.** Se tomaron capturas de cada menú con datos de ejemplo y se corrigieron detalles
(etiquetas del gráfico superpuestas, columnas apretadas). Una prueba Selenium recorre los 13 menús y verifica que la
consola del navegador quede sin errores.

> Patrón que se repite en cada módulo: **datos → lógica → API → pantalla → pruebas**. Si entiendes un módulo,
> entiendes todos.
