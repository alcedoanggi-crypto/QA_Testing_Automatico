/**
 * Analizar URL: lanza el análisis en el servidor (Chrome sin interfaz), espera el resultado y muestra los
 * errores de consola, JavaScript y red. Los errores seleccionados se convierten en novedades.
 */
(function () {
    "use strict";

    var QA = window.QA;
    var $ = QA.$;
    var esc = QA.esc;

    var SCANS_ENDPOINT = "/api/v1/scans";
    var POLL_MS = 1500;
    var TYPE_LABELS = { console: "Consola", javascript: "JavaScript", network: "Red", navegador: "Navegador" };
    var state = { scan: null, polling: null, historyTimer: null, shotUrl: null };

    function statusClass(status) {
        return { "Sin errores": "pill-success", "Con errores": "pill-danger", "Error": "pill-danger",
            "En curso": "pill-running" }[status] || "";
    }

    // ------------------------------------------------------------------ lanzar análisis
    function submitScan(event) {
        event.preventDefault();
        var url = $("scan-url").value.trim();
        var targetId = $("scan-target").value;
        if (!url && !targetId) {
            $("scan-url").classList.add("is-invalid");
            QA.setMsg("scan-msg", "Escribe la URL a analizar, por ejemplo http://localhost:3000", "error");
            return;
        }
        $("scan-url").classList.remove("is-invalid");
        var button = $("btn-scan");
        QA.setLoading(button, true, "Analizando");
        QA.setMsg("scan-msg", "Abriendo la aplicación en Chrome…", "info");
        QA.api.post(SCANS_ENDPOINT, {
            url: url, target_id: targetId || null,
            max_pages: Number($("scan-pages").value) || 1,
            wait_seconds: $("scan-wait").value,
            auto_incidents: $("scan-auto").checked
        }).then(function (scan) {
            waitForScan(scan.scan_id, Date.now());
        }).catch(function (err) {
            QA.handleError(err, "scan-msg");
            QA.setLoading(button, false, "Analizar");
        });
    }

    function waitForScan(scanId, started) {
        clearTimeout(state.polling);
        QA.api.get(SCANS_ENDPOINT + "/" + scanId).then(function (scan) {
            if (scan.status === "En curso") {
                var seconds = Math.round((Date.now() - started) / 1000);
                QA.setMsg("scan-msg", scanId + ": analizando " + scan.url + "… " + seconds + " s", "info");
                state.polling = setTimeout(function () { waitForScan(scanId, started); }, POLL_MS);
                return;
            }
            QA.setLoading($("btn-scan"), false, "Analizar");
            var total = scan.errors + scan.network_errors;
            QA.setMsg("scan-msg", scanId + " terminado: " + (scan.status === "Error" ? scan.message
                : total ? total + " error(es) y " + scan.warnings + " advertencia(s)." : "sin errores."),
                scan.status === "Sin errores" ? "success" : "error");
            renderScan(scan);
            history.replaceState(null, "", "#analizador/" + scanId);
            loadHistory();
            QA.emit("data-changed");
            QA.emit("incidents-changed");
        }).catch(function (err) {
            QA.setLoading($("btn-scan"), false, "Analizar");
            QA.handleError(err, "scan-msg");
        });
    }

    // ------------------------------------------------------------------ resultado
    function loadScan(scanId) {
        return QA.api.get(SCANS_ENDPOINT + "/" + encodeURIComponent(scanId))
            .then(function (scan) {
                renderScan(scan);
                if (scan.status === "En curso") {
                    QA.setLoading($("btn-scan"), true, "Analizando");
                    waitForScan(scan.scan_id, Date.now());
                }
            })
            .catch(function (err) { QA.handleError(err); });
    }

    function renderScan(scan) {
        state.scan = scan;
        $("scan-result").hidden = false;
        $("scan-result-title").textContent = scan.scan_id + " · " + scan.url;
        $("scan-result-meta").textContent = [scan.target_name, scan.engine, scan.page_title ? "«" + scan.page_title + "»" : "",
            scan.pages_scanned ? scan.pages_scanned + " página(s)" : "", scan.trigger, scan.executed_by, scan.started_at]
            .filter(Boolean).join(" · ");
        var pill = $("scan-result-status");
        pill.textContent = scan.status;
        pill.className = "pill " + statusClass(scan.status);
        $("scan-stat-errors").textContent = scan.errors;
        $("scan-stat-network").textContent = scan.network_errors;
        $("scan-stat-warnings").textContent = scan.warnings;
        $("scan-stat-http").textContent = scan.http_status || "—";
        $("scan-stat-load").textContent = scan.load_ms != null ? QA.fmt(scan.load_ms) : "—";
        $("scan-result-message").textContent = scan.message || "";
        renderIssues(scan.issues || []);
        loadScreenshot(scan);
    }

    function renderIssues(issues) {
        var tbody = $("table-scan-issues").querySelector("tbody");
        $("scan-select-all").checked = false;
        var pending = issues.filter(function (i) { return !i.incident_id; }).length;
        $("btn-scan-incidents").disabled = !pending;
        if (!issues.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="empty">No se detectaron errores en la consola ni en la red.</td></tr>';
            return;
        }
        tbody.innerHTML = issues.map(function (i) {
            var where = i.resource_url || i.page_url;
            return '<tr class="issue-' + esc(i.level) + '">' +
                "<td>" + (i.incident_id ? "" : '<input type="checkbox" class="issue-check" value="' + i.id +
                    '" aria-label="Seleccionar error">') + "</td>" +
                '<td><span class="pill ' + (i.level === "error" ? "pill-danger" : "pill-running") + '">' +
                esc(TYPE_LABELS[i.source] || i.source) + "</span></td>" +
                '<td class="issue-msg"><code>' + esc(i.message) + "</code>" +
                (i.location ? '<span class="cell-sub">' + esc(i.location) + "</span>" : "") + "</td>" +
                '<td class="issue-where" title="' + esc(where) + '">' + esc(where) + "</td>" +
                "<td>" + (i.incident_code ? '<a href="#novedades/' + i.incident_id + '">' + esc(i.incident_code) + "</a>" : "—") +
                "</td></tr>";
        }).join("");
    }

    function loadScreenshot(scan) {
        var figure = $("scan-shot");
        if (state.shotUrl) { URL.revokeObjectURL(state.shotUrl); state.shotUrl = null; }
        figure.hidden = true;
        if (!scan.has_screenshot) { return; }
        QA.api.fetch(SCANS_ENDPOINT + "/" + scan.scan_id + "/screenshot")
            .then(function (response) { return response.ok ? response.blob() : null; })
            .then(function (blob) {
                if (!blob || !state.scan || state.scan.scan_id !== scan.scan_id) { return; }
                state.shotUrl = URL.createObjectURL(blob);
                $("scan-shot-img").src = state.shotUrl;
                figure.hidden = false;
            })
            .catch(function () { /* la captura es opcional */ });
    }

    function createIncidents() {
        var ids = Array.prototype.map.call(document.querySelectorAll(".issue-check:checked"), function (c) {
            return Number(c.value);
        });
        if (!ids.length) {
            QA.toast("Selecciona los errores que quieres pasar a los programadores", "error");
            return;
        }
        var button = $("btn-scan-incidents");
        button.disabled = true;
        QA.api.post(SCANS_ENDPOINT + "/" + state.scan.scan_id + "/incidents", {
            issue_ids: ids,
            developer_id: $("scan-assign-dev").value || null,
            notify: $("scan-notify").checked
        }).then(function (res) {
            var parts = [];
            if (res.created.length) { parts.push(res.created.length + " novedad(es) creada(s)"); }
            if (res.repeated.length) { parts.push(res.repeated.length + " ya existían (" + res.repeated.join(", ") + ")"); }
            if (res.notified.length) { parts.push("enviadas: " + res.notified.join(", ")); }
            if ($("scan-notify").checked && !res.notified.length && res.created.length) {
                parts.push("no se enviaron: configura correo o webhook y asigna un programador");
            }
            QA.toast(parts.join(" · ") || "Sin cambios", "success");
            QA.emit("incidents-changed");
            QA.emit("data-changed");
            return loadScan(state.scan.scan_id);
        }).catch(function (err) {
            QA.handleError(err);
            button.disabled = false;
        });
    }

    // ------------------------------------------------------------------ historial
    function loadHistory() {
        clearTimeout(state.historyTimer);
        return QA.api.get(SCANS_ENDPOINT).then(function (scans) {
            var tbody = $("table-scans").querySelector("tbody");
            tbody.innerHTML = scans.length ? scans.map(function (s) {
                return '<tr data-scan-id="' + esc(s.scan_id) + '">' +
                    "<td>" + esc(s.scan_id) + "</td>" +
                    '<td class="cell-url" title="' + esc(s.url) + '">' + esc(s.url) + "</td>" +
                    "<td>" + esc(s.target_name || "—") + "</td>" +
                    '<td><span class="pill ' + statusClass(s.status) + '">' + esc(s.status) + "</span></td>" +
                    '<td class="num">' + s.errors + "</td>" +
                    '<td class="num">' + s.network_errors + "</td>" +
                    '<td class="num">' + s.warnings + "</td>" +
                    "<td>" + esc(s.trigger) + "</td>" +
                    "<td>" + esc(s.started_at) + "</td>" +
                    '<td class="actions-col"><div class="row-actions">' +
                    '<button type="button" class="btn-mini" data-act="view">Ver</button>' +
                    '<button type="button" class="btn-mini" data-act="rerun">Repetir</button>' +
                    '<button type="button" class="btn-mini btn-mini-danger" data-act="delete">Eliminar</button>' +
                    "</div></td></tr>";
            }).join("") : '<tr><td colspan="10" class="empty">Sin análisis todavía.</td></tr>';
            var running = scans.some(function (s) { return s.status === "En curso"; });
            if (running && QA.route().view === "analizador") {
                state.historyTimer = setTimeout(loadHistory, 4000);
            }
        }).catch(function (err) { QA.handleError(err); });
    }

    function onHistoryClick(event) {
        var button = event.target.closest("button[data-act]");
        if (!button) { return; }
        var row = button.closest("tr");
        var scanId = row.dataset.scanId;
        if (button.dataset.act === "view") {
            QA.go("analizador", scanId);
            $("scan-result").scrollIntoView({ behavior: "smooth" });
        } else if (button.dataset.act === "rerun") {
            $("scan-url").value = row.querySelector(".cell-url").textContent;
            $("scan-target").value = "";
            window.scrollTo({ top: 0, behavior: "smooth" });
            $("form-scan").requestSubmit();
        } else if (button.dataset.act === "delete") {
            QA.confirm("¿Eliminar el análisis " + scanId + " y sus errores registrados? Las novedades creadas se conservan.")
                .then(function (ok) {
                    if (!ok) { return; }
                    return QA.api.del(SCANS_ENDPOINT + "/" + scanId).then(function () {
                        QA.toast(scanId + " eliminado", "success");
                        if (state.scan && state.scan.scan_id === scanId) {
                            $("scan-result").hidden = true;
                            state.scan = null;
                            history.replaceState(null, "", "#analizador");
                        }
                        QA.emit("data-changed");
                        return loadHistory();
                    });
                })
                .catch(function (err) { QA.handleError(err); });
        }
    }

    // ------------------------------------------------------------------ init
    document.addEventListener("DOMContentLoaded", function () {
        if (!window.QAAuth.getToken()) { return; }

        QA.on("targets", function (targets) {
            QA.fillSelect($("scan-target"), targets.map(function (t) {
                return { value: String(t.id), label: t.name + " (" + t.url + ")" };
            }));
            $("scan-url-options").innerHTML = targets.map(function (t) {
                return '<option value="' + esc(t.url) + '">' + esc(t.name) + "</option>";
            }).join("");
        });
        QA.on("developers", function () { QA.fillSelect($("scan-assign-dev"), QA.developerOptions(true)); });
        QA.on("view:analizador", function (route) {
            if (route.changed) { loadHistory(); }
            if (route.param && (!state.scan || state.scan.scan_id !== route.param)) { loadScan(route.param); }
        });

        $("form-scan").addEventListener("submit", submitScan);
        $("scan-target").addEventListener("change", function () {
            var target = QA.cache.targets.filter(function (t) { return String(t.id) === $("scan-target").value; })[0];
            if (target) {
                $("scan-url").value = target.url;
                $("scan-pages").value = target.max_pages;
            }
        });
        $("scan-select-all").addEventListener("change", function () {
            var checked = $("scan-select-all").checked;
            document.querySelectorAll(".issue-check").forEach(function (c) { c.checked = checked; });
        });
        $("btn-scan-incidents").addEventListener("click", createIncidents);
        $("btn-scans-refresh").addEventListener("click", loadHistory);
        $("table-scans").addEventListener("click", onHistoryClick);
    });
})();
