# Guía de aprendizaje de QA Center

Esta guía explica **cómo se construyó QA Center** y **la lógica de cada parte**, para que puedas entender el código,
modificarlo y construir algo parecido por tu cuenta.

Está pensada para alguien que ya hace pruebas (Postman, Selenium, casos de prueba) y quiere entender cómo funciona por
dentro una aplicación web completa: servidor, base de datos, API, pantalla y pruebas automatizadas.

## Cómo leerla

Lee los capítulos en orden. Cada uno indica los archivos que explica; ábrelos al lado mientras lees.

| # | Capítulo | Qué aprendes |
|---|---|---|
| 1 | [Visión general y cómo se construyó](01-vision-general.md) | Qué hace la aplicación, tecnologías, arquitectura, carpetas y el orden en que se construyó |
| 2 | [Backend: servidor, seguridad y datos](02-backend.md) | Flask, rutas, JWT, validación, SQLite, logs |
| 3 | [Lógica de los módulos](03-modulos.md) | Analizador de URL, novedades, notificaciones, importación, automatización, reportes y documentación QA |
| 4 | [Frontend: la pantalla](04-frontend.md) | Página única con menú, rutas con `#`, llamadas a la API, formularios y diálogos |
| 5 | [Base de datos](05-base-de-datos.md) | Tablas, columnas y cómo se relacionan |
| 6 | [Pruebas automatizadas](06-pruebas.md) | Cómo se prueba la propia aplicación: unitarias, API y Selenium |
| 7 | [Práctica: recorridos, cambios y ejercicios](07-practica.md) | Seguir una petición de punta a punta, agregar un campo o un menú, ejercicios y problemas comunes |

## Acceso

| Dato | Valor |
|---|---|
| Carpeta del proyecto | `C:\Users\Pc\Downloads\qa-center` |
| Guía de aprendizaje | `C:\Users\Pc\Downloads\qa-center\docs\` |
| Video | `C:\Users\Pc\Downloads\qa-center\docs\video\qa-center-paso-a-paso.mp4` |
| Base de datos y archivos | `C:\Users\Pc\Downloads\qa-center\backend\data\` |
| Dirección | http://127.0.0.1:5000 |
| Usuario (correo) | `admin@test.com` |
| Contraseña | `SecurePassword123` |

Cómo agregar más usuarios: capítulo 7.1. Video paso a paso del uso: [`video/qa-center-paso-a-paso.mp4`](video/qa-center-paso-a-paso.mp4).

## Antes de empezar

```bash
cd C:\Users\Pc\Downloads\qa-center
.venv\Scripts\activate
python backend/app.py        # abre http://127.0.0.1:5000  (admin@test.com / SecurePassword123)
python -m pytest tests/ -v   # corre las 54 pruebas
```

Consejo: mientras lees, ten la aplicación abierta y las herramientas de desarrollo del navegador (F12) en la pestaña
**Red**. Cada clic que hagas mostrará la petición a la API que se explica en la guía.
