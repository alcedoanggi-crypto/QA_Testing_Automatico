/**
 * Núcleo compartido del panel: llamadas a la API con JWT, menú y rutas (#vista/param), eventos entre
 * módulos, diálogos, avisos y catálogos (ambientes, herramientas, severidades, programadores…).
 * Expone window.QA.
 */
(function () {
    "use strict";

    var listeners = {};
    var cache = { catalogs: null, developers: [], targets: [] };

    function $(id) { return document.getElementById(id); }

    function esc(value) {
        return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
            return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
        });
    }

    function fmt(value, decimals) {
        return Number(value || 0).toLocaleString("es-ES", {
            minimumFractionDigits: decimals || 0,
            maximumFractionDigits: decimals || 0
        });
    }

    // ------------------------------------------------------------------ eventos
    function on(name, fn) { (listeners[name] = listeners[name] || []).push(fn); }
    function emit(name, data) { (listeners[name] || []).forEach(function (fn) { fn(data); }); }

    // ------------------------------------------------------------------ API
    function isSessionError(err) { return err && err.message && err.message.indexOf("Sesión") === 0; }

    function authFetch(url, options) {
        var token = window.QAAuth.getToken();
        if (!token) {
            window.QAAuth.logout();
            return Promise.reject(new Error("Sesión no iniciada"));
        }
        options = options || {};
        options.headers = options.headers || {};
        options.headers["Authorization"] = "Bearer " + token;
        return fetch(url, options).catch(function () {
            throw new Error("No se pudo conectar con el servidor de QA Center. ¿Está en ejecución?");
        }).then(function (response) {
            if (response.status === 401) {
                window.QAAuth.logout();
                throw new Error("Sesión expirada");
            }
            return response;
        });
    }

    function request(method, url, payload) {
        var options = { method: method, headers: { "Accept": "application/json" } };
        if (payload instanceof FormData) {
            options.body = payload;
        } else if (payload !== undefined) {
            options.headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(payload);
        }
        return authFetch(url, options).then(function (response) {
            return response.json().catch(function () { return {}; }).then(function (body) {
                if (!response.ok) {
                    var err = new Error(body.error || "Error HTTP " + response.status);
                    err.status = response.status;
                    err.body = body;
                    throw err;
                }
                return body;
            });
        });
    }

    function filenameFromDisposition(header, fallback) {
        if (!header) { return fallback; }
        var match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header);
        return match ? decodeURIComponent(match[1]) : fallback;
    }

    function download(url, fallbackName) {
        return authFetch(url).then(function (response) {
            if (!response.ok) {
                return response.json().catch(function () { return {}; }).then(function (body) {
                    throw new Error(body.error || "Error al generar el archivo (HTTP " + response.status + ")");
                });
            }
            var filename = filenameFromDisposition(response.headers.get("Content-Disposition"), fallbackName);
            return response.blob().then(function (blob) {
                var link = document.createElement("a");
                var objectUrl = URL.createObjectURL(blob);
                link.href = objectUrl;
                link.download = filename;
                document.body.appendChild(link);
                link.click();
                link.remove();
                setTimeout(function () { URL.revokeObjectURL(objectUrl); }, 2000);
                return filename;
            });
        });
    }

    var api = {
        get: function (url) { return request("GET", url); },
        post: function (url, payload) { return request("POST", url, payload || {}); },
        put: function (url, payload) { return request("PUT", url, payload || {}); },
        del: function (url) { return request("DELETE", url); },
        upload: function (url, formData) { return request("POST", url, formData); },
        fetch: authFetch,
        download: download
    };

    // ------------------------------------------------------------------ UI helpers
    function setMsg(id, message, kind) {
        var el = typeof id === "string" ? $(id) : id;
        if (!el) { return; }
        el.textContent = message || "";
        el.className = (el.classList.contains("export-status") ? "export-status" : "form-msg") + (kind ? " is-" + kind : "");
    }

    function setLoading(button, isLoading, label) {
        button.disabled = isLoading;
        button.classList.toggle("is-loading", isLoading);
        var span = button.querySelector(".btn-label");
        if (label && span) { span.textContent = label; }
    }

    var toastTimer;
    function toast(message, kind) {
        var el = $("toast");
        el.textContent = message;
        el.className = "toast" + (kind ? " toast-" + kind : "");
        el.hidden = false;
        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () { el.hidden = true; }, 4000);
    }

    function handleError(err, target) {
        if (isSessionError(err)) { return; }
        if (target) { setMsg(target, err.message, "error"); } else { toast(err.message, "error"); }
    }

    function openDialog(id) {
        var dialog = $(id);
        if (!dialog.open) { dialog.showModal(); }
        return dialog;
    }

    function closeDialog(id) {
        var dialog = $(id);
        if (dialog.open) { dialog.close(); }
    }

    function confirmAction(text, yesLabel) {
        return new Promise(function (resolve) {
            var dialog = openDialog("dlg-confirm");
            $("confirm-text").textContent = text;
            $("btn-confirm-yes").textContent = yesLabel || "Eliminar";
            function finish(result) {
                $("btn-confirm-yes").removeEventListener("click", yes);
                $("btn-confirm-no").removeEventListener("click", no);
                dialog.removeEventListener("close", no);
                closeDialog("dlg-confirm");
                resolve(result);
            }
            function yes() { finish(true); }
            function no() { finish(false); }
            $("btn-confirm-yes").addEventListener("click", yes);
            $("btn-confirm-no").addEventListener("click", no);
            dialog.addEventListener("close", no);
        });
    }

    function fillSelect(select, items, options) {
        options = options || {};
        var keep = options.keepFirst === false ? 0 : (select.options.length && select.options[0].value === "" ? 1 : 0);
        var current = select.value;
        while (select.options.length > keep) { select.remove(keep); }
        items.forEach(function (item) {
            var option = document.createElement("option");
            if (typeof item === "object") {
                option.value = item.value;
                option.textContent = item.label;
            } else {
                option.value = item;
                option.textContent = item;
            }
            select.appendChild(option);
        });
        if (options.value !== undefined) {
            select.value = options.value;
        } else if (Array.prototype.some.call(select.options, function (o) { return o.value === current; })) {
            select.value = current;
        }
    }

    var SEVERITY_CLASS = { "Crítica": "sev-critical", "Alta": "sev-high", "Media": "sev-medium", "Baja": "sev-low" };
    var STATUS_CLASS = {
        "Nueva": "st-new", "Asignada": "st-assigned", "En progreso": "st-progress", "Resuelta": "st-resolved",
        "Verificada": "st-verified", "Cerrada": "st-closed", "Reabierta": "st-reopened"
    };

    function severityPill(value) { return '<span class="pill ' + (SEVERITY_CLASS[value] || "") + '">' + esc(value) + "</span>"; }
    function statusPill(value) { return '<span class="pill ' + (STATUS_CLASS[value] || "") + '">' + esc(value) + "</span>"; }
    function runStatus(value) {
        return '<span class="status ' + (value === "Passed" ? "status-passed" : "status-failed") + '">' + esc(value) + "</span>";
    }

    function toInputDateTime(value) { return value ? value.replace(" ", "T").slice(0, 16) : ""; }

    // ------------------------------------------------------------------ catálogos y datos compartidos
    function loadCatalogs() {
        if (cache.catalogs) { return Promise.resolve(cache.catalogs); }
        return api.get("/api/v1/catalogs").then(function (data) {
            cache.catalogs = data;
            emit("catalogs", data);
            return data;
        });
    }

    function refreshDevelopers() {
        return api.get("/api/v1/developers").then(function (list) {
            cache.developers = list;
            emit("developers", list);
            return list;
        });
    }

    function refreshTargets() {
        return api.get("/api/v1/targets").then(function (list) {
            cache.targets = list;
            emit("targets", list);
            return list;
        });
    }

    function developerOptions(onlyActive) {
        return cache.developers.filter(function (d) { return !onlyActive || d.active; }).map(function (d) {
            return { value: String(d.id), label: d.name + (d.area ? " · " + d.area : "") };
        });
    }

    // ------------------------------------------------------------------ rutas
    var DEFAULT_VIEW = "resumen";
    var current = { view: null, param: null };

    function parseHash() {
        var hash = (window.location.hash || "").replace(/^#/, "");
        var parts = hash.split("/");
        var view = parts[0] && $("view-" + parts[0]) ? parts[0] : DEFAULT_VIEW;
        return { view: view, param: parts[1] ? decodeURIComponent(parts[1]) : null };
    }

    function showRoute() {
        var route = parseHash();
        var changed = route.view !== current.view;
        current = route;
        document.querySelectorAll(".view").forEach(function (section) {
            section.hidden = section.dataset.view !== route.view;
        });
        document.querySelectorAll("[data-nav]").forEach(function (link) {
            var active = link.dataset.nav === route.view;
            link.classList.toggle("active", active);
            if (active) { link.setAttribute("aria-current", "page"); } else { link.removeAttribute("aria-current"); }
        });
        document.body.classList.remove("nav-open");
        $("btn-menu").setAttribute("aria-expanded", "false");
        if (changed) { window.scrollTo(0, 0); }
        emit("view:" + route.view, { param: route.param, changed: changed });
        emit("route", route);
    }

    function go(view, param) {
        var hash = "#" + view + (param ? "/" + encodeURIComponent(param) : "");
        if (window.location.hash === hash) { showRoute(); } else { window.location.hash = hash; }
    }

    // ------------------------------------------------------------------ init
    document.addEventListener("DOMContentLoaded", function () {
        if (!window.QAAuth.getToken()) { return; }
        document.querySelectorAll("dialog [data-close]").forEach(function (button) {
            button.addEventListener("click", function () { button.closest("dialog").close(); });
        });
        $("btn-menu").addEventListener("click", function () {
            var open = document.body.classList.toggle("nav-open");
            $("btn-menu").setAttribute("aria-expanded", open ? "true" : "false");
        });
        window.addEventListener("hashchange", showRoute);
        loadCatalogs().then(function () {
            return Promise.all([refreshDevelopers(), refreshTargets()]);
        }).catch(function (err) { handleError(err); });
        // Los módulos registran sus manejadores en DOMContentLoaded; la ruta se resuelve después.
        setTimeout(showRoute, 0);
    });

    window.QA = {
        $: $, esc: esc, fmt: fmt, on: on, emit: emit, api: api, cache: cache,
        setMsg: setMsg, setLoading: setLoading, toast: toast, handleError: handleError, isSessionError: isSessionError,
        openDialog: openDialog, closeDialog: closeDialog, confirm: confirmAction, fillSelect: fillSelect,
        severityPill: severityPill, statusPill: statusPill, runStatus: runStatus, toInputDateTime: toInputDateTime,
        loadCatalogs: loadCatalogs, refreshDevelopers: refreshDevelopers, refreshTargets: refreshTargets,
        developerOptions: developerOptions, go: go, route: function () { return current; }
    };
})();
