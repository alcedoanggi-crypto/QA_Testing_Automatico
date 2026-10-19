/**
 * Resumen: tarjetas de métricas, gráfico por suite (canvas nativo), tabla de ejecuciones con filtros,
 * novedades prioritarias, pruebas automáticas del sistema y exportación de reportes de ejecuciones.
 */
(function () {
    "use strict";

    var QA = window.QA;
    var $ = QA.$;
    var esc = QA.esc;
    var formatNumber = QA.fmt;

    var METRICS_ENDPOINT = "/api/v1/dashboard/metrics";
    var EXPORT_ENDPOINT = "/api/v1/reports/export";
    var EXECUTE_ENDPOINT = "/api/v1/test-runs/execute";
    var AUTO_REFRESH_MS = 15000;
    var FORMAT_LABELS = { pdf: "PDF", excel: "Excel", csv: "CSV" };
    var COLORS = { pass: "#16a34a", fail: "#dc2626", skip: "#94a3b8", grid: "#e2e8f0", text: "#64748b" };

    var state = { runs: [], bySuite: [], lastBatchId: null };

    function showError(message) {
        var box = $("dashboard-error");
        box.textContent = message;
        box.hidden = !message;
    }

    // ------------------------------------------------------------------ Métricas
    function loadMetrics() {
        var refreshBtn = $("btn-refresh");
        refreshBtn.disabled = true;
        return QA.api.get(METRICS_ENDPOINT)
            .then(function (data) {
                showError("");
                renderCards(data);
                renderIncidents(data.incidents, data.scans);
                renderAutomation(data.automation || {});
                renderLastBatch(data.last_batch);
                state.runs = data.recent_executions || [];
                state.bySuite = data.by_suite || [];
                populateFilterOptions();
                renderTable();
                drawChart();
                QA.emit("metrics", data);
            })
            .catch(function (err) {
                if (!QA.isSessionError(err)) { showError(err.message); }
            })
            .then(function () { refreshBtn.disabled = false; });
    }

    function renderCards(data) {
        $("value-total-tests").textContent = formatNumber(data.total_tests);
        $("value-total-executions").textContent = formatNumber(data.total_executions);
        $("value-pass-rate").textContent = formatNumber(data.pass_rate, 2) + " %";
        $("pass-rate-bar").style.width = Math.min(Math.max(data.pass_rate, 0), 100) + "%";
        $("value-bugs-found").textContent = formatNumber(data.bugs_found);
        $("value-skipped").textContent = formatNumber(data.skipped);
        $("value-avg-response").textContent = formatNumber(data.avg_response_time_ms, 0);
        $("last-updated").textContent = data.generated_at;
    }

    function renderIncidents(incidents, scans) {
        if (incidents) {
            var bySev = incidents.by_severity_open || {};
            var byStatus = incidents.by_status || {};
            $("value-open-incidents").textContent = formatNumber(incidents.open);
            $("value-unassigned").textContent = formatNumber(incidents.unassigned);
            $("value-high-incidents").textContent = formatNumber((bySev["Crítica"] || 0) + (bySev["Alta"] || 0));
            $("value-resolved").textContent = formatNumber((byStatus["Resuelta"] || 0) + (byStatus["Verificada"] || 0) +
                (byStatus["Cerrada"] || 0));
            var badge = $("nav-open-incidents");
            badge.textContent = incidents.open;
            badge.hidden = !incidents.open;
            $("priority-incidents").innerHTML = incidents.recent.length ? incidents.recent.map(function (i) {
                return '<li><a href="#novedades/' + i.id + '">' + QA.severityPill(i.severity) +
                    ' <span class="mini-title">' + esc(i.code) + " · " + esc(i.title) + "</span></a>" +
                    '<span class="muted small">' + esc(i.status) + " · " + esc(i.developer_name || "Sin asignar") + "</span></li>";
            }).join("") : '<li class="muted small">No hay novedades abiertas.</li>';
        }
        if (scans) {
            $("value-scans").textContent = formatNumber(scans.total);
            $("value-scan-issues").textContent = formatNumber(scans.issues);
        }
    }

    // ------------------------------------------------------------------ Tabla + filtros
    function populateFilterOptions() {
        var suites = uniqueValues("suite");
        QA.fillSelect($("filter-suite"), suites);
        QA.fillSelect($("filter-environment"), uniqueValues("environment"));
        $("suite-options").innerHTML = suites.map(function (s) {
            return '<option value="' + esc(s) + '"></option>';
        }).join("");
    }

    function uniqueValues(key) {
        var seen = {};
        state.runs.forEach(function (r) { seen[r[key]] = true; });
        return Object.keys(seen).sort();
    }

    function filteredRuns() {
        var search = $("filter-search").value.trim().toLowerCase();
        var suite = $("filter-suite").value;
        var status = $("filter-status").value;
        var environment = $("filter-environment").value;
        return state.runs.filter(function (r) {
            if (suite && r.suite !== suite) { return false; }
            if (status && r.status !== status) { return false; }
            if (environment && r.environment !== environment) { return false; }
            if (search) {
                var haystack = (r.run_id + " " + r.suite + " " + r.tool + " " + r.executed_by + " " + r.environment).toLowerCase();
                if (haystack.indexOf(search) === -1) { return false; }
            }
            return true;
        });
    }

    function renderTable() {
        var rows = filteredRuns();
        var tbody = $("table-test-runs-body");
        $("table-count").textContent = rows.length;
        if (!rows.length) {
            var message = state.runs.length
                ? "No hay ejecuciones que coincidan con los filtros."
                : "Aún no hay ejecuciones. Registra resultados o espera la ejecución automática.";
            tbody.innerHTML = '<tr><td colspan="13" class="empty">' + message + "</td></tr>";
            return;
        }
        tbody.innerHTML = rows.map(function (r) {
            return "<tr data-run-id=\"" + esc(r.run_id) + "\">" +
                "<td>" + esc(r.run_id) + "</td>" +
                "<td>" + esc(r.suite) + "</td>" +
                "<td>" + esc(r.tool) + "</td>" +
                "<td>" + esc(r.environment) + "</td>" +
                "<td>" + QA.runStatus(r.status) + "</td>" +
                "<td class=\"num\">" + formatNumber(r.total) + "</td>" +
                "<td class=\"num\">" + formatNumber(r.passed) + "</td>" +
                "<td class=\"num\">" + formatNumber(r.failed) + "</td>" +
                "<td class=\"num\">" + formatNumber(r.pass_rate, 2) + " %</td>" +
                "<td class=\"num\">" + formatNumber(r.avg_response_ms) + "</td>" +
                "<td>" + esc(r.executed_by) + "</td>" +
                "<td>" + esc(r.trigger) + "</td>" +
                "<td>" + esc(r.executed_at) + "</td>" +
                "</tr>";
        }).join("");
    }

    // ------------------------------------------------------------------ Gráfico
    function drawChart() {
        var canvas = $("chart-suites");
        var wrapper = canvas.parentElement;
        if (!wrapper.clientWidth) { return; }  // vista oculta: se dibuja al mostrarla
        var dpr = window.devicePixelRatio || 1;
        var width = wrapper.clientWidth;
        var height = wrapper.clientHeight;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        var ctx = canvas.getContext("2d");
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, width, height);

        var data = state.bySuite;
        $("chart-empty").hidden = data.length > 0;
        if (!data.length) { return; }

        var pad = { top: 10, right: 10, bottom: 30, left: 44 };
        var plotW = width - pad.left - pad.right;
        var plotH = height - pad.top - pad.bottom;
        var maxValue = Math.max.apply(null, data.map(function (s) { return s.total; })) || 1;
        // Paso "redondo" (1, 2 o 5 x 10^n), entero, para unas 4 divisiones.
        var rawStep = maxValue / 4;
        var magnitude = Math.pow(10, Math.floor(Math.log10(rawStep)));
        var ratio = rawStep / magnitude;
        var step = Math.max(1, (ratio <= 1 ? 1 : ratio <= 2 ? 2 : ratio <= 5 ? 5 : 10) * magnitude);
        var niceMax = Math.ceil(maxValue / step) * step;

        ctx.font = "12px Segoe UI, system-ui, sans-serif";
        ctx.textBaseline = "middle";
        for (var value = 0; value <= niceMax; value += step) {
            var y = pad.top + plotH - (value / niceMax) * plotH;
            ctx.strokeStyle = COLORS.grid;
            ctx.beginPath();
            ctx.moveTo(pad.left, y);
            ctx.lineTo(width - pad.right, y);
            ctx.stroke();
            ctx.fillStyle = COLORS.text;
            ctx.textAlign = "right";
            ctx.fillText(formatNumber(value), pad.left - 8, y);
        }

        var slot = plotW / data.length;
        var barW = Math.min(48, slot * 0.6);
        data.forEach(function (s, idx) {
            var x = pad.left + slot * idx + (slot - barW) / 2;
            var base = pad.top + plotH;
            [["passed", COLORS.pass], ["failed", COLORS.fail], ["skipped", COLORS.skip]].forEach(function (seg) {
                var h = (s[seg[0]] / niceMax) * plotH;
                if (h <= 0) { return; }
                ctx.fillStyle = seg[1];
                ctx.fillRect(x, base - h, barW, h);
                base -= h;
            });
            ctx.fillStyle = COLORS.text;
            ctx.textAlign = "center";
            // Recorta la etiqueta para que quepa en su columna sin solaparse con la vecina.
            var label = s.suite;
            while (label.length > 3 && ctx.measureText(label).width > slot - 8) {
                label = label.slice(0, -2) + "…";
                label = label.replace(/…+$/, "…");
            }
            ctx.fillText(label, pad.left + slot * idx + slot / 2, height - pad.bottom / 2);
        });
    }

    // ------------------------------------------------------------------ Pruebas automáticas
    function formatTime(dateTime) {
        return dateTime ? dateTime.split(" ")[1] : "—";
    }

    function renderAutomation(automation) {
        var badge = $("automation-badge");
        var info = $("automation-info");
        if (automation.running) {
            badge.textContent = "Ejecutando…";
            badge.className = "pill pill-running";
        } else if (automation.enabled) {
            badge.textContent = "Activo";
            badge.className = "pill pill-success";
        } else {
            badge.textContent = "Manual";
            badge.className = "pill";
        }
        if (automation.enabled) {
            info.textContent = "El sistema se prueba solo cada " + formatNumber(automation.interval_minutes) +
                " min y registra los resultados. Próxima ejecución: " + formatTime(automation.next_run_at) + ".";
        } else {
            info.textContent = "La ejecución programada está desactivada. Usa el botón para probar el sistema.";
        }
        if (automation.last_error) {
            info.textContent += " Último error: " + automation.last_error;
        }
    }

    function renderLastBatch(batch) {
        $("last-run").hidden = !batch;
        $("last-run-empty").hidden = !!batch;
        if (!batch) { return; }
        $("last-run-date").textContent = batch.executed_at;
        $("last-run-meta").textContent = batch.batch_id + " · " + batch.trigger + " · " + batch.executed_by;
        $("last-run-passed").textContent = batch.passed + " exitosos";
        $("last-run-failed").textContent = batch.failed + " fallidos";
        $("last-run-failed").hidden = batch.failed === 0;
        if (state.lastBatchId === batch.batch_id) { return; }
        state.lastBatchId = batch.batch_id;
        // Los casos fallidos se muestran primero.
        var cases = batch.cases.slice().sort(function (a, b) {
            return (a.status === "Failed" ? 0 : 1) - (b.status === "Failed" ? 0 : 1);
        });
        $("last-run-cases").innerHTML = cases.map(caseItem).join("");
    }

    function caseItem(c) {
        var passed = c.status === "Passed";
        var skipped = c.status === "Skipped";
        return '<li class="case ' + (passed ? "case-passed" : skipped ? "case-skipped" : "case-failed") + '">' +
            '<span class="case-icon">' + (passed ? "✓" : skipped ? "–" : "✗") + "</span>" +
            '<div class="case-body">' +
            '<span class="case-name">' + esc(c.name) + "</span>" +
            '<span class="case-meta">' + esc(c.suite) + " · " + formatNumber(c.response_ms, 1) + " ms</span>" +
            (c.detail ? '<span class="case-detail">' + esc(c.detail) + "</span>" : "") +
            "</div></li>";
    }
    QA.caseItem = caseItem;

    function runSystemTests() {
        var button = $("btn-run-tests");
        QA.setLoading(button, true, "Ejecutando pruebas");
        QA.setMsg("run-tests-status", "Probando login, seguridad, métricas, reportes y vistas…", "info");
        QA.api.post(EXECUTE_ENDPOINT)
            .then(function (result) {
                QA.setMsg("run-tests-status", "Lote " + result.batch_id + ": " + result.passed + "/" + result.total +
                    " casos exitosos" + (result.failed ? " (" + result.failed + " fallidos)" : "") + ".",
                    result.failed ? "error" : "success");
                return loadMetrics();
            })
            .catch(function (err) { QA.handleError(err, "run-tests-status"); })
            .then(function () { QA.setLoading(button, false, "Ejecutar pruebas ahora"); });
    }

    // ------------------------------------------------------------------ Exportación
    function exportReport(format, button) {
        var label = FORMAT_LABELS[format] || format.toUpperCase();
        button.disabled = true;
        QA.setMsg("export-status", "Generando reporte " + label + "…");
        QA.api.download(EXPORT_ENDPOINT + "?format=" + encodeURIComponent(format), "reporte_pruebas")
            .then(function (filename) {
                QA.setMsg("export-status", "Reporte " + label + " descargado: " + filename, "success");
            })
            .catch(function (err) { QA.handleError(err, "export-status"); })
            .then(function () { button.disabled = false; });
    }

    // ------------------------------------------------------------------ Init
    document.addEventListener("DOMContentLoaded", function () {
        if (!window.QAAuth.getToken()) {
            window.QAAuth.logout();
            return;
        }

        var user = window.QAAuth.getUser() || {};
        $("user-name").textContent = user.name || "Usuario";
        $("user-role").textContent = user.role || "";

        ["filter-search", "filter-suite", "filter-status", "filter-environment"].forEach(function (id) {
            $(id).addEventListener(id === "filter-search" ? "input" : "change", renderTable);
        });

        ["btn-export-pdf", "btn-export-excel", "btn-export-csv"].forEach(function (id) {
            var button = $(id);
            button.addEventListener("click", function () { exportReport(button.dataset.format, button); });
        });

        $("btn-refresh").addEventListener("click", loadMetrics);
        $("btn-run-tests").addEventListener("click", runSystemTests);

        var resizeTimer;
        window.addEventListener("resize", function () {
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(drawChart, 150);
        });
        QA.on("view:resumen", function () { drawChart(); });
        QA.on("data-changed", loadMetrics);

        loadMetrics();
        setInterval(loadMetrics, AUTO_REFRESH_MS);
    });
})();
