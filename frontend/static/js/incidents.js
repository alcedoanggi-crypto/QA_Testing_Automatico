/**
 * Novedades: listado con filtros y acciones masivas, alta/edición/eliminación, detalle con historial y
 * comentarios, y envío al programador (correo SMTP, webhook, correo propio o copiar texto).
 */
(function () {
    "use strict";

    var QA = window.QA;
    var $ = QA.$;
    var esc = QA.esc;

    var ENDPOINT = "/api/v1/incidents";
    var state = { list: [], tab: "open", detail: null, loaded: false, counts: null, reopenId: null };

    // ------------------------------------------------------------------ listado
    function currentFilters() {
        var params = {};
        if (state.tab === "open") { params.open = "1"; } else if (state.tab !== "all") { params.status = state.tab; }
        var map = { q: "inc-search", severity: "inc-filter-severity", developer_id: "inc-filter-developer",
            source: "inc-filter-source", environment: "inc-filter-environment" };
        Object.keys(map).forEach(function (key) {
            var value = $(map[key]).value.trim();
            if (value) { params[key] = value; }
        });
        return params;
    }

    function queryString(params) {
        return Object.keys(params).map(function (k) {
            return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]);
        }).join("&");
    }

    function loadIncidents() {
        return QA.api.get(ENDPOINT + "?" + queryString(currentFilters()))
            .then(function (list) {
                state.list = list;
                state.loaded = true;
                renderTable();
            })
            .catch(function (err) { QA.handleError(err); });
    }

    function renderTabs() {
        var statuses = (QA.cache.catalogs || {}).incident_statuses || [];
        var counts = state.counts || {};
        var openCount = ["Nueva", "Asignada", "En progreso", "Reabierta"].reduce(function (sum, s) {
            return sum + (counts[s] || 0);
        }, 0);
        var tabs = [{ key: "open", label: "Abiertas", n: openCount }, { key: "all", label: "Todas" }].concat(
            statuses.map(function (s) { return { key: s, label: s, n: counts[s] }; }));
        $("incident-status-tabs").innerHTML = tabs.map(function (t) {
            return '<button type="button" class="tab' + (state.tab === t.key ? " active" : "") + '" data-tab="' + esc(t.key) +
                '" aria-pressed="' + (state.tab === t.key) + '">' + esc(t.label) +
                (t.n != null && state.counts ? ' <span class="tab-count">' + t.n + "</span>" : "") + "</button>";
        }).join("");
    }

    function renderTable() {
        var tbody = $("table-incidents").querySelector("tbody");
        $("inc-count").textContent = state.list.length;
        $("inc-select-all").checked = false;
        updateBulk();
        if (!state.list.length) {
            tbody.innerHTML = '<tr><td colspan="9" class="empty">No hay novedades con estos filtros.</td></tr>';
            return;
        }
        tbody.innerHTML = state.list.map(function (i) {
            return '<tr data-incident-id="' + i.id + '">' +
                '<td><input type="checkbox" class="inc-check" value="' + i.id + '" aria-label="Seleccionar ' + esc(i.code) + '"></td>' +
                "<td>" + esc(i.code) + "</td>" +
                '<td class="cell-title"><a href="#novedades/' + i.id + '" class="cell-main">' + esc(i.title) + "</a>" +
                '<span class="cell-sub">' + esc([i.module, i.environment, i.occurrences > 1 ? i.occurrences + " veces" : ""]
                    .filter(Boolean).join(" · ")) + "</span></td>" +
                "<td>" + QA.severityPill(i.severity) + "</td>" +
                "<td>" + QA.statusPill(i.status) + "</td>" +
                "<td>" + (i.developer_name ? esc(i.developer_name) : '<span class="muted">Sin asignar</span>') +
                (i.notified_at ? '<span class="cell-sub">Enviada ' + esc(i.notified_at.slice(0, 16)) + "</span>" : "") + "</td>" +
                "<td>" + esc(i.source) + "</td>" +
                "<td>" + esc(i.created_at.slice(0, 16)) + "</td>" +
                '<td class="actions-col"><div class="row-actions">' +
                '<button type="button" class="btn-mini" data-act="view">Ver</button>' +
                '<button type="button" class="btn-mini" data-act="edit">Editar</button>' +
                '<button type="button" class="btn-mini btn-mini-danger" data-act="delete">Eliminar</button>' +
                "</div></td></tr>";
        }).join("");
    }

    function selectedIds() {
        return Array.prototype.map.call(document.querySelectorAll(".inc-check:checked"), function (c) { return Number(c.value); });
    }

    function updateBulk() {
        var n = selectedIds().length;
        $("inc-bulk").hidden = n === 0;
        $("inc-selected-count").textContent = n;
    }

    function bulk(payload, confirmText) {
        var ids = selectedIds();
        if (!ids.length) { return; }
        payload.ids = ids;
        var go = confirmText ? QA.confirm(confirmText, payload.action === "delete" ? "Eliminar" : "Confirmar") : Promise.resolve(true);
        go.then(function (ok) {
            if (!ok) { return; }
            return QA.api.post(ENDPOINT + "/bulk", payload).then(function (res) {
                QA.toast(res.updated + " novedad(es) actualizada(s)", "success");
                changed();
            });
        }).catch(function (err) { QA.handleError(err); }).then(function () {
            $("inc-bulk-dev").value = "";
            $("inc-bulk-status").value = "";
        });
    }

    function changed() {
        QA.emit("data-changed");
        loadIncidents();
        QA.refreshDevelopers();
    }

    // ------------------------------------------------------------------ formulario
    var FORM_FIELDS = {
        title: "inc-title", severity: "inc-severity", priority: "inc-priority", status: "inc-status",
        environment: "inc-environment", developer_id: "inc-developer", module: "inc-module", due_date: "inc-due",
        url: "inc-url", description: "inc-description", steps: "inc-steps", expected: "inc-expected", actual: "inc-actual"
    };

    function openForm(incident) {
        var isEdit = !!(incident && incident.id);
        $("form-incident").reset();
        QA.setMsg("inc-msg", "");
        $("inc-id").value = isEdit ? incident.id : "";
        $("dlg-incident-title").textContent = isEdit ? "Editar " + incident.code : "Nueva novedad";
        $("inc-notify-row").hidden = isEdit;
        var defaults = { severity: "Media", priority: "Normal", status: "Nueva", environment: "QA" };
        Object.keys(FORM_FIELDS).forEach(function (key) {
            var value = incident && incident[key] != null ? incident[key] : (defaults[key] || "");
            $(FORM_FIELDS[key]).value = String(value);
        });
        QA.openDialog("dlg-incident");
        $("inc-title").focus();
    }

    function submitForm(event) {
        event.preventDefault();
        var payload = {};
        Object.keys(FORM_FIELDS).forEach(function (key) { payload[key] = $(FORM_FIELDS[key]).value.trim(); });
        payload.developer_id = payload.developer_id || null;
        if (!payload.title) {
            QA.setMsg("inc-msg", "El título es obligatorio.", "error");
            $("inc-title").focus();
            return;
        }
        var id = $("inc-id").value;
        if (!id) { payload.notify = $("inc-notify").checked; }
        var button = $("btn-inc-save");
        QA.setLoading(button, true);
        (id ? QA.api.put(ENDPOINT + "/" + id, payload) : QA.api.post(ENDPOINT, payload))
            .then(function (incident) {
                QA.closeDialog("dlg-incident");
                QA.toast("Novedad " + incident.code + (id ? " actualizada" : " registrada"), "success");
                changed();
                if (id && String(state.reopenId) === id) { QA.go("novedades", id); }
                state.reopenId = null;
            })
            .catch(function (err) { QA.handleError(err, "inc-msg"); })
            .then(function () { QA.setLoading(button, false); });
    }

    function deleteIncident(incident) {
        return QA.confirm("¿Eliminar la novedad " + incident.code + " «" + incident.title + "» y su historial?")
            .then(function (ok) {
                if (!ok) { return false; }
                return QA.api.del(ENDPOINT + "/" + incident.id).then(function () {
                    QA.toast("Novedad " + incident.code + " eliminada", "success");
                    changed();
                    return true;
                });
            })
            .catch(function (err) { QA.handleError(err); return false; });
    }

    // ------------------------------------------------------------------ detalle
    function openDetail(id) {
        return QA.api.get(ENDPOINT + "/" + id).then(function (incident) {
            state.detail = incident;
            renderDetail(incident);
            QA.openDialog("dlg-detail");
        }).catch(function (err) {
            QA.handleError(err);
            history.replaceState(null, "", "#novedades");
        });
    }

    function renderDetail(i) {
        $("detail-code").textContent = i.code + " · " + i.source + (i.source_ref ? " " + i.source_ref : "");
        $("detail-title").textContent = i.title;
        $("detail-pills").innerHTML = QA.severityPill(i.severity) + QA.statusPill(i.status) +
            '<span class="pill">Prioridad ' + esc(i.priority) + "</span>" + '<span class="pill">' + esc(i.environment) + "</span>" +
            (i.occurrences > 1 ? '<span class="pill pill-running">Detectada ' + i.occurrences + " veces</span>" : "");
        $("detail-status").value = i.status;
        $("detail-developer").value = i.developer_id ? String(i.developer_id) : "";
        var fields = [
            ["Módulo", i.module], ["URL", i.url ? '<a href="' + esc(i.url) + '" target="_blank" rel="noopener">' + esc(i.url) + "</a>" : "", true],
            ["Fecha límite", i.due_date], ["Reportada por", i.reported_by + " · " + i.created_at],
            ["Última actualización", i.updated_at], ["Último envío", i.notified_at],
            ["Descripción", i.description], ["Pasos para reproducir", i.steps],
            ["Resultado esperado", i.expected], ["Resultado actual / error", i.actual]
        ];
        $("detail-fields").innerHTML = fields.filter(function (f) { return f[1]; }).map(function (f) {
            return "<dt>" + esc(f[0]) + "</dt><dd>" + (f[2] ? f[1] : esc(f[1])) + "</dd>";
        }).join("");

        var channels = i.share.channels;
        var labels = { email: "Correo a " + (i.developer_email || "— (sin programador asignado)"), webhook: "Webhook (Slack / Teams / Discord)" };
        $("detail-channels").innerHTML = channels.length ? channels.map(function (c) {
            var disabled = c === "email" && !i.developer_email;
            return '<label class="check"><input type="checkbox" name="channel" value="' + c + '"' + (disabled ? " disabled" : " checked") +
                "> " + esc(labels[c]) + "</label>";
        }).join("") : '<p class="muted small">No hay correo SMTP ni webhook configurados. Usa «Abrir en mi correo» o ' +
            '«Copiar texto», o configúralos en <a href="#configuracion">Configuración</a>.</p>';
        $("btn-detail-send").hidden = !channels.length;
        $("detail-note").hidden = !channels.length;
        $("btn-detail-mailto").href = "mailto:" + encodeURIComponent(i.developer_email || "") +
            "?subject=" + encodeURIComponent(i.share.subject) + "&body=" + encodeURIComponent(i.share.message);
        QA.setMsg("detail-share-msg", i.developer_id ? "" : "Asigna un programador para enviarle la novedad.", i.developer_id ? "" : "info");

        $("detail-history").innerHTML = i.history.map(function (h) {
            return '<li class="tl-' + esc(h.kind.toLowerCase().replace(/\s+/g, "-").normalize("NFD").replace(/[̀-ͯ]/g, "")) + '">' +
                '<span class="tl-head"><strong>' + esc(h.kind) + "</strong> · " + esc(h.author) + " · " + esc(h.created_at) + "</span>" +
                '<span class="tl-body">' + esc(h.detail) + "</span></li>";
        }).join("");
    }

    function quickUpdate(payload) {
        QA.api.put(ENDPOINT + "/" + state.detail.id, payload)
            .then(function () { changed(); return openDetail(state.detail.id); })
            .catch(function (err) { QA.handleError(err, "detail-share-msg"); renderDetail(state.detail); });
    }

    function sendDetail() {
        var channels = Array.prototype.map.call(document.querySelectorAll("#detail-channels input:checked"), function (c) { return c.value; });
        if (!channels.length) {
            QA.setMsg("detail-share-msg", "Elige al menos un canal.", "error");
            return;
        }
        var button = $("btn-detail-send");
        button.disabled = true;
        QA.setMsg("detail-share-msg", "Enviando…", "info");
        QA.api.post(ENDPOINT + "/" + state.detail.id + "/notify", { channels: channels, note: $("detail-note").value.trim() })
            .then(function (res) { return res; }, function (err) { if (err.body && err.body.results) { return err.body; } throw err; })
            .then(function (res) {
                var ok = Object.keys(res.results).filter(function (c) { return res.results[c] === "ok"; });
                var bad = Object.keys(res.results).filter(function (c) { return res.results[c] !== "ok"; });
                $("detail-note").value = "";
                return openDetail(state.detail.id).then(function () {
                    QA.setMsg("detail-share-msg", (ok.length ? "Enviada por " + ok.join(" y ") + ". " : "") +
                        bad.map(function (c) { return res.results[c]; }).join(" "), bad.length ? "error" : "success");
                    changed();
                });
            })
            .catch(function (err) { QA.handleError(err, "detail-share-msg"); })
            .then(function () { button.disabled = false; });
    }

    function recordManualShare(channel) {
        QA.api.post(ENDPOINT + "/" + state.detail.id + "/notify", { manual_channel: channel })
            .then(function () { return openDetail(state.detail.id); })
            .then(function () { changed(); })
            .catch(function (err) { QA.handleError(err); });
    }

    function copyDetail() {
        var text = state.detail.share.subject + "\n\n" + state.detail.share.message;
        var done = function () {
            QA.setMsg("detail-share-msg", "Texto copiado. Pégalo en el chat o correo del programador.", "success");
            recordManualShare("texto copiado");
        };
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).then(done, function () { fallbackCopy(text); done(); });
        } else {
            fallbackCopy(text);
            done();
        }
    }

    function fallbackCopy(text) {
        var area = document.createElement("textarea");
        area.value = text;
        area.style.position = "fixed";
        area.style.opacity = "0";
        $("dlg-detail").appendChild(area);
        area.select();
        try { document.execCommand("copy"); } catch (e) { /* sin portapapeles */ }
        area.remove();
    }

    function submitComment(event) {
        event.preventDefault();
        var input = $("detail-comment");
        var text = input.value.trim();
        if (!text) { return; }
        QA.api.post(ENDPOINT + "/" + state.detail.id + "/comments", { text: text })
            .then(function () { input.value = ""; return openDetail(state.detail.id); })
            .catch(function (err) { QA.handleError(err); });
    }

    // ------------------------------------------------------------------ exportación
    function exportIncidents(format, button) {
        var params = currentFilters();
        params.format = format;
        button.disabled = true;
        QA.setMsg("export-inc-status", "Generando archivo…");
        QA.api.download(ENDPOINT + "/export?" + queryString(params), "novedades")
            .then(function (filename) { QA.setMsg("export-inc-status", "Descargado: " + filename, "success"); })
            .catch(function (err) { QA.handleError(err, "export-inc-status"); })
            .then(function () { button.disabled = false; });
    }

    // ------------------------------------------------------------------ init
    document.addEventListener("DOMContentLoaded", function () {
        if (!window.QAAuth.getToken()) { return; }

        QA.on("catalogs", function (c) {
            QA.fillSelect($("inc-severity"), c.severities);
            QA.fillSelect($("inc-priority"), c.priorities);
            QA.fillSelect($("inc-status"), c.incident_statuses);
            QA.fillSelect($("inc-environment"), c.environments);
            QA.fillSelect($("detail-status"), c.incident_statuses);
            QA.fillSelect($("inc-filter-severity"), c.severities);
            QA.fillSelect($("inc-filter-source"), c.incident_sources);
            QA.fillSelect($("inc-filter-environment"), c.environments);
            QA.fillSelect($("inc-bulk-status"), c.incident_statuses);
            renderTabs();
        });
        QA.on("developers", function () {
            var all = QA.developerOptions(false);
            QA.fillSelect($("inc-developer"), all);
            QA.fillSelect($("detail-developer"), all);
            QA.fillSelect($("inc-bulk-dev"), [{ value: "none", label: "— Quitar asignación —" }].concat(QA.developerOptions(true)));
            QA.fillSelect($("inc-filter-developer"), [{ value: "none", label: "Sin asignar" }].concat(all));
        });
        QA.on("metrics", function (data) {
            if (data.incidents) { state.counts = data.incidents.by_status; renderTabs(); }
        });
        QA.on("view:novedades", function (route) {
            if (route.changed || !state.loaded) { loadIncidents(); }
            if (route.param) { openDetail(route.param); }
        });
        QA.on("incidents-changed", function () { if (state.loaded) { loadIncidents(); } });

        $("btn-new-incident").addEventListener("click", function () { openForm(null); });
        $("form-incident").addEventListener("submit", submitForm);

        $("incident-status-tabs").addEventListener("click", function (event) {
            var tab = event.target.closest("[data-tab]");
            if (!tab) { return; }
            state.tab = tab.dataset.tab;
            renderTabs();
            loadIncidents();
        });
        var searchTimer;
        $("inc-search").addEventListener("input", function () {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(loadIncidents, 250);
        });
        ["inc-filter-severity", "inc-filter-developer", "inc-filter-source", "inc-filter-environment"].forEach(function (id) {
            $(id).addEventListener("change", loadIncidents);
        });

        $("table-incidents").addEventListener("change", function (event) {
            if (event.target.id === "inc-select-all") {
                document.querySelectorAll(".inc-check").forEach(function (c) { c.checked = event.target.checked; });
            }
            updateBulk();
        });
        $("table-incidents").addEventListener("click", function (event) {
            var button = event.target.closest("button[data-act]");
            if (!button) { return; }
            var id = Number(button.closest("tr").dataset.incidentId);
            var incident = state.list.filter(function (i) { return i.id === id; })[0];
            if (button.dataset.act === "view") { QA.go("novedades", id); }
            if (button.dataset.act === "edit") { openForm(incident); }
            if (button.dataset.act === "delete") { deleteIncident(incident); }
        });

        $("inc-bulk-dev").addEventListener("change", function () {
            var value = $("inc-bulk-dev").value;
            if (value) { bulk({ action: "assign", developer_id: value === "none" ? null : value }); }
        });
        $("inc-bulk-status").addEventListener("change", function () {
            var value = $("inc-bulk-status").value;
            if (value) { bulk({ action: "status", status: value }); }
        });
        $("btn-inc-bulk-notify").addEventListener("click", function () {
            bulk({ action: "notify" }, "¿Enviar las novedades seleccionadas a sus programadores por correo/webhook?");
        });
        $("btn-inc-bulk-delete").addEventListener("click", function () {
            bulk({ action: "delete" }, "¿Eliminar " + selectedIds().length + " novedad(es) y su historial?");
        });

        $("dlg-detail").addEventListener("close", function () {
            if (QA.route().view === "novedades" && QA.route().param) { history.replaceState(null, "", "#novedades"); }
            state.detail = null;
        });
        $("detail-status").addEventListener("change", function () { quickUpdate({ status: $("detail-status").value }); });
        $("detail-developer").addEventListener("change", function () {
            quickUpdate({ developer_id: $("detail-developer").value || null });
        });
        $("btn-detail-send").addEventListener("click", sendDetail);
        $("btn-detail-mailto").addEventListener("click", function () { recordManualShare("correo propio"); });
        $("btn-detail-copy").addEventListener("click", copyDetail);
        $("form-comment").addEventListener("submit", submitComment);
        $("btn-detail-edit").addEventListener("click", function () {
            var incident = state.detail;
            state.reopenId = incident.id;
            QA.closeDialog("dlg-detail");
            openForm(incident);
        });
        $("btn-detail-delete").addEventListener("click", function () {
            var incident = state.detail;
            deleteIncident(incident).then(function (deleted) { if (deleted) { QA.closeDialog("dlg-detail"); } });
        });

        $("btn-export-inc-excel").addEventListener("click", function () { exportIncidents("excel", this); });
        $("btn-export-inc-csv").addEventListener("click", function () { exportIncidents("csv", this); });
    });
})();
