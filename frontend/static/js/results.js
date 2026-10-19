/**
 * Resultados de pruebas externas (Postman, Selenium, Cypress…): registrar, editar, eliminar, importar
 * reportes (Newman JSON / JUnit XML), ver el detalle de casos y convertir fallas en novedades.
 */
(function () {
    "use strict";

    var QA = window.QA;
    var $ = QA.$;
    var esc = QA.esc;

    var RUNS_ENDPOINT = "/api/v1/test-runs";
    var state = { runs: [], loaded: false, casesRunId: null };

    // ------------------------------------------------------------------ listado
    function loadResults() {
        var origin = $("results-filter-origin").value;
        return QA.api.get(RUNS_ENDPOINT + (origin === "external" ? "?origin=external" : ""))
            .then(function (runs) {
                state.runs = runs;
                state.loaded = true;
                renderResults();
            })
            .catch(function (err) { QA.handleError(err); });
    }

    function renderResults() {
        var search = $("results-search").value.trim().toLowerCase();
        var rows = state.runs.filter(function (r) {
            if (!search) { return true; }
            return (r.run_id + " " + r.tool + " " + r.suite + " " + r.module + " " + r.environment + " " + r.notes)
                .toLowerCase().indexOf(search) !== -1;
        });
        var tbody = $("table-results").querySelector("tbody");
        if (!rows.length) {
            tbody.innerHTML = '<tr><td colspan="8" class="empty">' + (state.runs.length
                ? "Sin coincidencias." : "Aún no registras resultados. Usa el formulario o importa un archivo.") + "</td></tr>";
            return;
        }
        tbody.innerHTML = rows.map(function (r) {
            return '<tr data-result-id="' + esc(r.run_id) + '">' +
                "<td>" + esc(r.run_id) + "</td>" +
                "<td>" + esc(r.tool || "—") + "</td>" +
                '<td><span class="cell-main">' + esc(r.suite) + "</span>" +
                (r.module ? '<span class="cell-sub">' + esc(r.module) + "</span>" : "") + "</td>" +
                "<td>" + QA.runStatus(r.status) + "</td>" +
                '<td class="num">' + QA.fmt(r.passed) + "/" + QA.fmt(r.total) + "</td>" +
                '<td class="num">' + QA.fmt(r.failed) + "</td>" +
                "<td>" + esc(r.executed_at) + "</td>" +
                '<td class="actions-col"><div class="row-actions">' +
                '<button type="button" class="btn-mini" data-act="view">Ver</button>' +
                '<button type="button" class="btn-mini" data-act="edit">Editar</button>' +
                '<button type="button" class="btn-mini btn-mini-danger" data-act="delete">Eliminar</button>' +
                "</div></td></tr>";
        }).join("");
    }

    function findRun(runId) {
        return state.runs.filter(function (r) { return r.run_id === runId; })[0];
    }

    // ------------------------------------------------------------------ formulario
    function readNumber(id) {
        var value = $(id).value.trim();
        return value === "" ? 0 : Number(value);
    }

    function updatePassedPreview() {
        var passed = readNumber("run-total") - readNumber("run-failed") - readNumber("run-skipped");
        var preview = $("run-passed-preview");
        preview.textContent = isFinite(passed) ? passed : "—";
        preview.style.color = passed < 0 ? "var(--danger)" : "";
    }

    function resetForm() {
        $("form-register-run").reset();
        $("run-edit-id").value = "";
        $("run-tool").value = "Postman";
        $("run-environment").value = "QA";
        $("register-title").textContent = "Registrar resultado";
        $("btn-register-run").querySelector(".btn-label").textContent = "Registrar resultado";
        $("btn-cancel-edit").hidden = true;
        $("run-incident-row").hidden = false;
        $("run-suite").classList.remove("is-invalid");
        updatePassedPreview();
    }

    function startEdit(run) {
        $("run-edit-id").value = run.run_id;
        if (!Array.prototype.some.call($("run-tool").options, function (o) { return o.value === run.tool; })) {
            QA.fillSelect($("run-tool"), QA.cache.catalogs.tools.concat([run.tool]));
        }
        $("run-tool").value = run.tool;
        $("run-environment").value = run.environment;
        $("run-suite").value = run.suite;
        $("run-module").value = run.module || "";
        $("run-executed-at").value = QA.toInputDateTime(run.executed_at);
        $("run-url").value = run.url || "";
        $("run-total").value = run.total;
        $("run-failed").value = run.failed;
        $("run-skipped").value = run.skipped;
        $("run-response").value = run.avg_response_ms;
        $("run-duration").value = run.duration_s;
        $("run-notes").value = run.notes || "";
        $("run-evidence").value = run.evidence_url || "";
        $("register-title").textContent = "Editar " + run.run_id;
        $("btn-register-run").querySelector(".btn-label").textContent = "Guardar cambios";
        $("btn-cancel-edit").hidden = false;
        $("run-incident-row").hidden = true;
        QA.setMsg("register-run-msg", "");
        updatePassedPreview();
        $("panel-register").scrollIntoView({ behavior: "smooth", block: "start" });
        $("run-suite").focus();
    }

    function submitRun(event) {
        event.preventDefault();
        var payload = {
            tool: $("run-tool").value,
            suite: $("run-suite").value.trim(),
            environment: $("run-environment").value,
            module: $("run-module").value.trim(),
            executed_at: $("run-executed-at").value,
            url: $("run-url").value.trim(),
            total: readNumber("run-total"),
            failed: readNumber("run-failed"),
            skipped: readNumber("run-skipped"),
            avg_response_ms: readNumber("run-response"),
            duration_s: readNumber("run-duration"),
            notes: $("run-notes").value.trim(),
            evidence_url: $("run-evidence").value.trim()
        };
        if (!payload.suite) {
            $("run-suite").classList.add("is-invalid");
            QA.setMsg("register-run-msg", "Indica el nombre de la suite.", "error");
            return;
        }
        $("run-suite").classList.remove("is-invalid");
        var editId = $("run-edit-id").value;
        var createIncident = !editId && $("run-create-incident").checked && payload.failed > 0;
        var developerId = $("run-incident-dev").value;
        var button = $("btn-register-run");
        QA.setLoading(button, true);
        var call = editId ? QA.api.put(RUNS_ENDPOINT + "/" + encodeURIComponent(editId), payload)
            : QA.api.post(RUNS_ENDPOINT, payload);
        call.then(function (run) {
            var message = editId ? "Ejecución " + run.run_id + " actualizada (" + run.status + ")."
                : "Ejecución " + run.run_id + " registrada (" + run.status + ").";
            if (!createIncident) { return message; }
            return QA.api.post(RUNS_ENDPOINT + "/" + run.run_id + "/incidents", { developer_id: developerId || null })
                .then(function (res) {
                    return message + " Novedad creada: " + res.created.map(function (i) { return i.code; }).join(", ") + ".";
                });
        }).then(function (message) {
            resetForm();
            QA.setMsg("register-run-msg", message, "success");
            QA.emit("data-changed");
            QA.emit("incidents-changed");
            return loadResults();
        }).catch(function (err) {
            QA.handleError(err, "register-run-msg");
        }).then(function () { QA.setLoading(button, false); });
    }

    function deleteRun(run) {
        QA.confirm("¿Eliminar la ejecución " + run.run_id + " (" + run.suite + ")? Esta acción no se puede deshacer.")
            .then(function (ok) {
                if (!ok) { return; }
                return QA.api.del(RUNS_ENDPOINT + "/" + encodeURIComponent(run.run_id)).then(function () {
                    QA.toast("Ejecución " + run.run_id + " eliminada", "success");
                    if ($("run-edit-id").value === run.run_id) { resetForm(); }
                    QA.emit("data-changed");
                    return loadResults();
                });
            })
            .catch(function (err) { QA.handleError(err); });
    }

    // ------------------------------------------------------------------ detalle de casos
    function showCases(runId) {
        state.casesRunId = runId;
        QA.api.get(RUNS_ENDPOINT + "/" + encodeURIComponent(runId)).then(function (run) {
            $("cases-title").textContent = run.run_id + " · " + run.suite;
            $("cases-meta").textContent = [run.tool, run.environment, run.module, run.executed_at, run.executed_by,
                run.passed + "/" + run.total + " exitosas", run.url].filter(Boolean).join(" · ");
            var notes = [run.notes, run.evidence_url ? "Evidencia: " + run.evidence_url : ""].filter(Boolean).join("\n");
            $("cases-notes").textContent = notes;
            $("cases-notes").hidden = !notes;
            var cases = run.cases.slice().sort(function (a, b) {
                return (a.status === "Failed" ? 0 : 1) - (b.status === "Failed" ? 0 : 1);
            });
            $("cases-list").innerHTML = cases.length ? cases.map(QA.caseItem).join("")
                : '<li class="case muted">Registro sin detalle de casos (resultado ingresado a mano).</li>';
            $("btn-cases-incident").hidden = run.failed === 0;
            QA.openDialog("dlg-cases");
        }).catch(function (err) { QA.handleError(err); });
    }

    function casesToIncidents() {
        var button = $("btn-cases-incident");
        button.disabled = true;
        QA.api.post(RUNS_ENDPOINT + "/" + state.casesRunId + "/incidents", {})
            .then(function (res) {
                QA.closeDialog("dlg-cases");
                QA.toast(res.created.length ? "Novedades creadas: " + res.created.map(function (i) { return i.code; }).join(", ")
                    : "Las fallas ya tenían novedades abiertas (se registró la reaparición).", "success");
                QA.emit("incidents-changed");
                QA.emit("data-changed");
            })
            .catch(function (err) { QA.handleError(err); })
            .then(function () { button.disabled = false; });
    }

    // ------------------------------------------------------------------ importación
    function submitImport(event) {
        event.preventDefault();
        var file = $("import-file").files[0];
        if (!file) {
            QA.setMsg("import-msg", "Selecciona el archivo de resultados.", "error");
            return;
        }
        var data = new FormData();
        data.append("file", file);
        data.append("tool", $("import-tool").value);
        data.append("environment", $("import-environment").value);
        data.append("suite", $("import-suite").value.trim());
        data.append("developer_id", $("import-dev").value);
        data.append("create_incidents", $("import-incidents").checked ? "1" : "0");
        var button = $("btn-import");
        QA.setLoading(button, true);
        QA.setMsg("import-msg", "Procesando " + file.name + "…", "info");
        QA.api.upload(RUNS_ENDPOINT + "/import", data)
            .then(function (run) {
                QA.setMsg("import-msg", run.run_id + " importada: " + run.passed + "/" + run.total + " exitosas (" +
                    run.tool + ")." + (run.incidents_created.length ? " Novedades: " + run.incidents_created.join(", ") : ""),
                    run.failed ? "error" : "success");
                $("form-import").reset();
                $("import-tool").value = "Selenium";
                $("import-environment").value = "QA";
                QA.emit("data-changed");
                QA.emit("incidents-changed");
                return loadResults();
            })
            .catch(function (err) { QA.handleError(err, "import-msg"); })
            .then(function () { QA.setLoading(button, false); });
    }

    // ------------------------------------------------------------------ init
    document.addEventListener("DOMContentLoaded", function () {
        if (!window.QAAuth.getToken()) { return; }

        QA.on("catalogs", function (c) {
            QA.fillSelect($("run-tool"), c.tools, { value: "Postman" });
            QA.fillSelect($("run-environment"), c.environments, { value: "QA" });
            QA.fillSelect($("import-tool"), c.tools, { value: "Selenium" });
            QA.fillSelect($("import-environment"), c.environments, { value: "QA" });
        });
        QA.on("developers", function () {
            QA.fillSelect($("run-incident-dev"), QA.developerOptions(true));
            QA.fillSelect($("import-dev"), QA.developerOptions(true));
        });
        QA.on("view:resultados", function () { loadResults(); });
        QA.on("data-changed", function () { if (state.loaded) { loadResults(); } });

        $("form-register-run").addEventListener("submit", submitRun);
        $("btn-cancel-edit").addEventListener("click", function () { resetForm(); QA.setMsg("register-run-msg", ""); });
        ["run-total", "run-failed", "run-skipped"].forEach(function (id) {
            $(id).addEventListener("input", updatePassedPreview);
        });
        $("form-import").addEventListener("submit", submitImport);
        $("results-search").addEventListener("input", renderResults);
        $("results-filter-origin").addEventListener("change", loadResults);
        $("btn-cases-incident").addEventListener("click", casesToIncidents);

        $("table-results").addEventListener("click", function (event) {
            var button = event.target.closest("button[data-act]");
            if (!button) { return; }
            var run = findRun(button.closest("tr").dataset.resultId);
            if (!run) { return; }
            if (button.dataset.act === "view") { showCases(run.run_id); }
            if (button.dataset.act === "edit") { startEdit(run); }
            if (button.dataset.act === "delete") { deleteRun(run); }
        });
    });
})();
