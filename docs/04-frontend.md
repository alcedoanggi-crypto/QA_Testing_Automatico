# 4. Frontend: la pantalla

Archivos: `frontend/templates/*.html`, `frontend/static/js/*.js`, `frontend/static/css/styles.css`.

## 4.1 Una sola página con muchas vistas

`dashboard.html` contiene **todas** las pantallas a la vez, cada una dentro de una sección:

```html
<section id="view-resumen"  class="view" data-view="resumen">  ... </section>
<section id="view-casos"    class="view" data-view="casos" hidden> ... </section>
<section id="view-defectos" class="view" data-view="defectos" hidden> ... </section>
```

El menú son enlaces con `#`:

```html
<a href="#casos" data-nav="casos">Casos de prueba</a>
```

Al hacer clic, el navegador **no recarga la página**; solo cambia la parte final de la URL (`/dashboard#casos`) y
dispara el evento `hashchange`. Esto se llama *Single Page Application* (SPA): navegar es instantáneo y el estado
(filtros, datos cargados) se conserva.

## 4.2 `core.js`: lo común a todas las pantallas

Todos los demás archivos JS usan el objeto global `window.QA` que define `core.js`.

### El enrutador

```javascript
function showRoute() {
    var route = parseHash();                 // "#novedades/12" → {view: "novedades", param: "12"}
    document.querySelectorAll(".view").forEach(function (section) {
        section.hidden = section.dataset.view !== route.view;   // muestra solo una
    });
    document.querySelectorAll("[data-nav]").forEach(function (link) {
        link.classList.toggle("active", link.dataset.nav === route.view);   // resalta el menú
    });
    emit("view:" + route.view, { param: route.param, changed: changed });   // avisa al módulo
}
window.addEventListener("hashchange", showRoute);
```

El parámetro sirve para enlaces directos: `#novedades/12` abre la novedad 12; `#analizador/SCAN-1001` muestra ese
análisis. Por eso los mensajes enviados a los programadores incluyen un enlace que abre la novedad exacta.

### Eventos entre módulos

Los módulos no se llaman entre sí directamente; se avisan con eventos (patrón *publicar/suscribir*):

```javascript
function on(name, fn) { (listeners[name] = listeners[name] || []).push(fn); }
function emit(name, data) { (listeners[name] || []).forEach(function (fn) { fn(data); }); }
```

Ejemplos reales:

| Evento | Quién lo emite | Quién escucha y qué hace |
|---|---|---|
| `view:casos` | el enrutador | `docs.js` carga los casos |
| `data-changed` | cualquier módulo que guarda algo | `dashboard.js` recarga las métricas |
| `incidents-changed` | analizador, resultados, casos | `incidents.js` recarga la lista de novedades |
| `developers` | `core.js` al cargar programadores | todos los `<select>` de "Asignar a" se actualizan |
| `metrics` | `dashboard.js` | `incidents.js` (contadores) y `docs.js` (avance) |

Ventaja: agregar un módulo nuevo no obliga a modificar los existentes; solo escucha los eventos que le interesan.

### Llamadas a la API con el token

Todas las peticiones pasan por una sola función, que agrega el token y trata los errores igual en todas partes:

```javascript
function request(method, url, payload) {
    var options = { method: method, headers: { "Accept": "application/json" } };
    if (payload instanceof FormData) {
        options.body = payload;                         // archivos (multipart)
    } else if (payload !== undefined) {
        options.headers["Content-Type"] = "application/json";
        options.body = JSON.stringify(payload);
    }
    return authFetch(url, options).then(function (response) {   // authFetch agrega "Authorization: Bearer ..."
        return response.json().catch(function () { return {}; }).then(function (body) {
            if (!response.ok) { throw new Error(body.error || "Error HTTP " + response.status); }
            return body;
        });
    });
}
```

`authFetch` además: si el servidor responde **401** (token vencido) cierra la sesión y vuelve al login; si no hay
conexión, muestra "No se pudo conectar con el servidor de QA Center. ¿Está en ejecución?" (el antiguo
"Failed to fetch").

Uso desde cualquier módulo: `QA.api.get(url)`, `QA.api.post(url, datos)`, `QA.api.put(...)`, `QA.api.del(...)`,
`QA.api.upload(url, formData)` y `QA.api.download(url)`.

## 4.3 El patrón CRUD de cada pantalla

Todas las pantallas que registran, editan y eliminan siguen la misma receta. Ejemplo: Programadores (`people.js`).

**1. Un formulario con un campo oculto para el id.** Vacío = crear; con valor = editar.

```html
<form id="form-developer">
    <input id="dev-id" type="hidden">
    <input id="dev-name"> <input id="dev-email"> ...
</form>
```

**2. Al guardar, el id decide POST o PUT:**

```javascript
var id = $("dev-id").value;
(id ? QA.api.put("/api/v1/developers/" + id, payload)
    : QA.api.post("/api/v1/developers", payload))
    .then(function (dev) { QA.setMsg("dev-msg", dev.name + " registrado.", "success"); resetForm(); refresh(); })
    .catch(function (err) { QA.handleError(err, "dev-msg"); });   // muestra el mensaje del servidor
```

**3. Editar = rellenar el formulario** con los datos de la fila y poner el id.

**4. Eliminar siempre pide confirmación** con un diálogo propio (`QA.confirm`), que devuelve una promesa:

```javascript
QA.confirm("¿Eliminar a " + dev.name + "?").then(function (ok) {
    if (!ok) { return; }
    return QA.api.del("/api/v1/developers/" + id).then(refresh);
});
```

**5. Botones de la tabla con un solo escuchador** (*delegación de eventos*). En vez de un `addEventListener` por cada
botón (que habría que volver a poner cada vez que la tabla se redibuja), se escucha la tabla completa y se mira qué
botón se pulsó por su `data-act`:

```javascript
$("table-developers").addEventListener("click", function (event) {
    var button = event.target.closest("[data-act]");
    if (!button) { return; }
    var id = Number(button.closest("tr").dataset.devId);
    if (button.dataset.act === "edit") { ... }
    if (button.dataset.act === "delete") { ... }
});
```

## 4.4 Diálogos

Las ventanas emergentes (nueva novedad, ejecutar caso, detalle…) usan la etiqueta nativa `<dialog>`:

```javascript
$("dlg-case").showModal();   // abre con fondo oscuro, la tecla Esc la cierra
$("dlg-case").close();
```

Cualquier botón con el atributo `data-close` cierra su diálogo (se programa una sola vez en `core.js`).

## 4.5 Seguridad en la pantalla: escapar el texto

Los mensajes de error que captura el analizador vienen de **otras aplicaciones** y pueden contener HTML
(`<img src=x onerror=alert(1)>`). Si se insertaran tal cual con `innerHTML`, ese código se ejecutaría en QA Center
(ataque XSS). Por eso **todo texto que viene de datos pasa por `esc()`** antes de insertarse:

```javascript
function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
}
tbody.innerHTML = rows.map(function (r) { return "<td>" + esc(r.title) + "</td>"; }).join("");
```

## 4.6 Esperar un proceso largo (polling)

`scanner.js` pide el estado del análisis cada 1,5 s hasta que deja de estar "En curso", mostrando los segundos
transcurridos:

```javascript
function waitForScan(scanId, started) {
    QA.api.get("/api/v1/scans/" + scanId).then(function (scan) {
        if (scan.status === "En curso") {
            setTimeout(function () { waitForScan(scanId, started); }, 1500);   // vuelve a preguntar
            return;
        }
        renderScan(scan);   // terminó
    });
}
```

## 4.7 Imágenes y descargas protegidas

Una etiqueta `<img src="/api/v1/evidence/3">` no puede enviar el token JWT. Por eso las capturas y evidencias se piden
con `fetch` (que sí lleva el token), se convierten en un *blob* y se muestran con una URL temporal:

```javascript
QA.api.fetch(url).then(function (r) { return r.blob(); }).then(function (blob) {
    img.src = URL.createObjectURL(blob);
});
```

Las descargas de PDF/Excel usan la misma idea: `fetch` → blob → enlace `<a download>` invisible → `click()`.

## 4.8 Estilos (CSS)

- **Variables** en `:root` (`--primary`, `--danger`, `--border`…): cambiar un color en un lugar lo cambia en toda la
  aplicación.
- **CSS Grid** para las tarjetas y formularios (`grid-template-columns: repeat(4, 1fr)`).
- **Responsive** con `@media (max-width: …)`: en pantallas pequeñas el menú se oculta y aparece el botón ☰, y las
  columnas pasan a una sola.
- Clases de estado reutilizables: `.pill`, `.sev-high`, `.st-resolved`, `.chip-fallido`… para que el mismo estado
  tenga el mismo color en todas las pantallas.

## 4.9 Mapa de archivos JS

| Archivo | Menús que maneja |
|---|---|
| `auth.js` | Login, guardar/borrar el token, cerrar sesión |
| `core.js` | Lo común: API, rutas, eventos, diálogos, avisos, catálogos |
| `dashboard.js` | Resumen, Pruebas automáticas, exportación de ejecuciones |
| `scanner.js` | Analizar URL |
| `results.js` | Resultados Postman / Selenium |
| `incidents.js` | Novedades (y exportación de novedades) |
| `people.js` | Programadores y Aplicaciones |
| `settings.js` | Configuración |
| `docs.js` | Plan de pruebas, Casos de prueba, Matriz de trazabilidad, Reporte de defectos, Reportes |
