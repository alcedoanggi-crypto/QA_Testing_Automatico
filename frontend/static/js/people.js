/**
 * Programadores y Aplicaciones: registro, edición y eliminación; análisis inmediato y monitoreo automático.
 */
(function () {
    "use strict";

    var QA = window.QA;
    var $ = QA.$;
    var esc = QA.esc;

    // ================================================================== Programadores
    function renderDevelopers(list) {
        var tbody = $("table-developers").querySelector("tbody");
        if (!list.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty">Registra a los programadores para asignarles novedades.</td></tr>';
            return;
        }
        tbody.innerHTML = list.map(function (d) {
            return '<tr data-dev-id="' + d.id + '">' +
                '<td><span class="cell-main">' + esc(d.name) + "</span>" + (d.phone ? '<span class="cell-sub">' + esc(d.phone) + "</span>" : "") + "</td>" +
                '<td><a href="mailto:' + esc(d.email) + '">' + esc(d.email) + "</a></td>" +
                "<td>" + esc(d.area || "—") + "</td>" +
                '<td class="num">' + (d.open_incidents ? '<a href="#novedades" data-act="incidents">' + d.open_incidents + "</a>" : "0") + "</td>" +
                '<td class="num">' + d.total_incidents + "</td>" +
                '<td><span class="pill ' + (d.active ? "pill-success" : "") + '">' + (d.active ? "Activo" : "Inactivo") + "</span></td>" +
                '<td class="actions-col"><div class="row-actions">' +
                '<button type="button" class="btn-mini" data-act="edit">Editar</button>' +
                '<button type="button" class="btn-mini btn-mini-danger" data-act="delete">Eliminar</button>' +
                "</div></td></tr>";
        }).join("");
    }

    function resetDeveloperForm() {
        $("form-developer").reset();
        $("dev-id").value = "";
        $("dev-form-title").textContent = "Nuevo programador";
        $("btn-dev-cancel").hidden = true;
    }

    function submitDeveloper(event) {
        event.preventDefault();
        var payload = {
            name: $("dev-name").value.trim(), email: $("dev-email").value.trim(),
            area: $("dev-area").value.trim(), phone: $("dev-phone").value.trim(), active: $("dev-active").checked
        };
        if (!payload.name || !payload.email) {
            QA.setMsg("dev-msg", "Nombre y correo son obligatorios.", "error");
            return;
        }
        var id = $("dev-id").value;
        var button = $("btn-dev-save");
        QA.setLoading(button, true);
        (id ? QA.api.put("/api/v1/developers/" + id, payload) : QA.api.post("/api/v1/developers", payload))
            .then(function (dev) {
                QA.setMsg("dev-msg", dev.name + (id ? " actualizado." : " registrado."), "success");
                resetDeveloperForm();
                return QA.refreshDevelopers();
            })
            .catch(function (err) { QA.handleError(err, "dev-msg"); })
            .then(function () { QA.setLoading(button, false); });
    }

    function onDeveloperClick(event) {
        var el = event.target.closest("[data-act]");
        if (!el) { return; }
        var id = Number(el.closest("tr").dataset.devId);
        var dev = QA.cache.developers.filter(function (d) { return d.id === id; })[0];
        if (el.dataset.act === "incidents") {
            event.preventDefault();
            $("inc-filter-developer").value = String(id);
            QA.go("novedades");
            QA.emit("incidents-changed");
        } else if (el.dataset.act === "edit") {
            $("dev-id").value = dev.id;
            $("dev-name").value = dev.name;
            $("dev-email").value = dev.email;
            $("dev-area").value = dev.area;
            $("dev-phone").value = dev.phone;
            $("dev-active").checked = !!dev.active;
            $("dev-form-title").textContent = "Editar programador";
            $("btn-dev-cancel").hidden = false;
            QA.setMsg("dev-msg", "");
            $("dev-name").focus();
        } else if (el.dataset.act === "delete") {
            QA.confirm("¿Eliminar a " + dev.name + "? Sus " + dev.total_incidents + " novedad(es) quedarán sin asignar.")
                .then(function (ok) {
                    if (!ok) { return; }
                    return QA.api.del("/api/v1/developers/" + id).then(function () {
                        QA.toast(dev.name + " eliminado", "success");
                        if ($("dev-id").value === String(id)) { resetDeveloperForm(); }
                        QA.emit("incidents-changed");
                        return Promise.all([QA.refreshDevelopers(), QA.refreshTargets()]);
                    });
                })
                .catch(function (err) { QA.handleError(err); });
        }
    }

    // ================================================================== Aplicaciones
    function renderTargets(list) {
        var tbody = $("table-targets").querySelector("tbody");
        if (!list.length) {
            tbody.innerHTML = '<tr><td colspan="6" class="empty">Registra las URLs de las aplicaciones que pruebas (por ejemplo http://localhost:3000).</td></tr>';
            return;
        }
        tbody.innerHTML = list.map(function (t) {
            var last = t.last_scan_id
                ? '<a href="#analizador/' + esc(t.last_scan_id) + '">' + esc(t.last_scan_id) + "</a> " +
                  '<span class="pill ' + (t.last_scan_status === "Sin errores" ? "pill-success" : t.last_scan_status === "En curso" ? "pill-running" : "pill-danger") + '">' +
                  esc(t.last_scan_status === "Con errores" ? t.last_scan_errors + " errores" : t.last_scan_status) + "</span>" +
                  '<span class="cell-sub">' + esc(t.last_scan_at) + "</span>"
                : '<span class="muted">Nunca</span>';
            return '<tr data-target-id="' + t.id + '">' +
                '<td><span class="cell-main">' + esc(t.name) + '</span><span class="cell-sub">' + esc(t.environment) + "</span></td>" +
                '<td class="cell-url"><a href="' + esc(t.url) + '" target="_blank" rel="noopener">' + esc(t.url) + "</a></td>" +
                "<td>" + esc(t.developer_name || "—") + "</td>" +
                '<td><span class="pill ' + (t.monitor ? "pill-success" : "") + '">' + (t.monitor ? "Automático" : "Manual") + "</span></td>" +
                "<td>" + last + "</td>" +
                '<td class="actions-col"><div class="row-actions">' +
                '<button type="button" class="btn-mini" data-act="scan">Analizar</button>' +
                '<button type="button" class="btn-mini" data-act="edit">Editar</button>' +
                '<button type="button" class="btn-mini btn-mini-danger" data-act="delete">Eliminar</button>' +
                "</div></td></tr>";
        }).join("");
    }

    function resetTargetForm() {
        $("form-target").reset();
        $("target-id").value = "";
        $("target-environment").value = "Local";
        $("target-form-title").textContent = "Nueva aplicación";
        $("btn-target-cancel").hidden = true;
    }

    function submitTarget(event) {
        event.preventDefault();
        var payload = {
            name: $("target-name").value.trim(), url: $("target-url").value.trim(),
            environment: $("target-environment").value, max_pages: Number($("target-pages").value) || 1,
            developer_id: $("target-developer").value || null, notes: $("target-notes").value.trim(),
            monitor: $("target-monitor").checked
        };
        if (!payload.name || !payload.url) {
            QA.setMsg("target-msg", "Nombre y URL son obligatorios.", "error");
            return;
        }
        var id = $("target-id").value;
        var button = $("btn-target-save");
        QA.setLoading(button, true);
        (id ? QA.api.put("/api/v1/targets/" + id, payload) : QA.api.post("/api/v1/targets", payload))
            .then(function (target) {
                QA.setMsg("target-msg", target.name + (id ? " actualizada." : " registrada.") +
                    (target.monitor ? " Se analizará automáticamente." : ""), "success");
                resetTargetForm();
                return QA.refreshTargets();
            })
            .catch(function (err) { QA.handleError(err, "target-msg"); })
            .then(function () { QA.setLoading(button, false); });
    }

    function onTargetClick(event) {
        var button = event.target.closest("button[data-act]");
        if (!button) { return; }
        var id = Number(button.closest("tr").dataset.targetId);
        var target = QA.cache.targets.filter(function (t) { return t.id === id; })[0];
        if (button.dataset.act === "scan") {
            button.disabled = true;
            QA.api.post("/api/v1/scans", { target_id: id }).then(function (scan) {
                QA.toast("Analizando " + target.name + " (" + scan.scan_id + ")…", "info");
                QA.go("analizador", scan.scan_id);
            }).catch(function (err) { QA.handleError(err); }).then(function () { button.disabled = false; });
        } else if (button.dataset.act === "edit") {
            $("target-id").value = target.id;
            $("target-name").value = target.name;
            $("target-url").value = target.url;
            $("target-environment").value = target.environment;
            $("target-pages").value = target.max_pages;
            $("target-developer").value = target.developer_id ? String(target.developer_id) : "";
            $("target-notes").value = target.notes;
            $("target-monitor").checked = !!target.monitor;
            $("target-form-title").textContent = "Editar aplicación";
            $("btn-target-cancel").hidden = false;
            QA.setMsg("target-msg", "");
            $("target-name").focus();
        } else if (button.dataset.act === "delete") {
            QA.confirm("¿Eliminar la aplicación " + target.name + "? Su historial de análisis se conserva.")
                .then(function (ok) {
                    if (!ok) { return; }
                    return QA.api.del("/api/v1/targets/" + id).then(function () {
                        QA.toast(target.name + " eliminada", "success");
                        if ($("target-id").value === String(id)) { resetTargetForm(); }
                        return QA.refreshTargets();
                    });
                })
                .catch(function (err) { QA.handleError(err); });
        }
    }

    function loadMonitor() {
        QA.api.get("/api/v1/monitor").then(function (m) {
            $("monitor-info").textContent = m.enabled
                ? "Monitoreo automático activo: " + m.targets + " aplicación(es) cada " + QA.fmt(m.interval_minutes) +
                  " min. Próxima revisión: " + (m.running ? "en curso…" : m.next_run_at) + "."
                : "El monitoreo automático está desactivado en este servidor (QA_MONITOR=0). Puedes analizar manualmente.";
        }).catch(function () { /* informativo */ });
    }

    // ================================================================== init
    document.addEventListener("DOMContentLoaded", function () {
        if (!window.QAAuth.getToken()) { return; }

        QA.on("catalogs", function (c) { QA.fillSelect($("target-environment"), c.environments, { value: "Local" }); });
        QA.on("developers", function (list) {
            renderDevelopers(list);
            QA.fillSelect($("target-developer"), QA.developerOptions(false));
        });
        QA.on("targets", renderTargets);
        QA.on("view:programadores", function () { QA.refreshDevelopers(); });
        QA.on("view:aplicaciones", function () { QA.refreshTargets(); loadMonitor(); });

        $("form-developer").addEventListener("submit", submitDeveloper);
        $("btn-dev-cancel").addEventListener("click", function () { resetDeveloperForm(); QA.setMsg("dev-msg", ""); });
        $("table-developers").addEventListener("click", onDeveloperClick);

        $("form-target").addEventListener("submit", submitTarget);
        $("btn-target-cancel").addEventListener("click", function () { resetTargetForm(); QA.setMsg("target-msg", ""); });
        $("table-targets").addEventListener("click", onTargetClick);
        $("btn-monitor-run").addEventListener("click", function () {
            QA.api.post("/api/v1/monitor/run").then(function (res) {
                QA.toast(res.message, "success");
                loadMonitor();
            }).catch(function (err) { QA.handleError(err); });
        });
    });
})();
