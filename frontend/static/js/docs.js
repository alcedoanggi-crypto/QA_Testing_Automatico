/**
 * Documentación QA: Plan de pruebas, Casos de prueba (ejecución, evidencias, defectos), Matriz de trazabilidad y
 * Reporte de defectos. También los reportes descargables (por análisis, documentación y reportes automáticos).
 */
(function () {
    "use strict";

    var QA = window.QA;
    var $ = QA.$;
    var esc = QA.esc;

    var state = { catalogs: null, plans: [], requirements: [], cases: [], detail: null, execId: null };
    var CASE_STATUS_CLASS = { "Aprobado": "pill-success", "Fallido": "pill-danger", "Bloqueado": "pill-running",
        "Omitido": "", "No ejecutado": "st-new" };
    var COVERAGE_CLASS = { "Validado": "pill-success", "Con fallas": "pill-danger", "Sin cobertura": "pill-danger",
        "Bloqueado": "pill-running", "Pendiente": "st-new" };

    function casePill(status) { return '<span class="pill ' + (CASE_STATUS_CLASS[status] || "") + '">' + esc(status) + "</span>"; }
    function coveragePill(value) { return '<span class="pill ' + (COVERAGE_CLASS[value] || "") + '">' + esc(value) + "</span>"; }
    function bar(value, cls) {
        return '<div class="progress"><div class="progress-bar ' + (cls || "") + '" style="width:' + Math.min(100, value || 0) + '%"></div></div>';
    }
    function query(params) {
        return Object.keys(params).filter(function (k) { return params[k] !== "" && params[k] != null; })
            .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(params[k]); }).join("&");
    }
    function download(url, statusId) {
        if (statusId) { QA.setMsg(statusId, "Generando documento…"); }
        return QA.api.download(url, "documento")
            .then(function (name) {
                if (statusId) { QA.setMsg(statusId, "Descargado: " + name, "success"); } else { QA.toast("Descargado: " + name, "success"); }
            })
            .catch(function (err) { QA.handleError(err, statusId); });
    }
    function stats(containerId, items) {
        $(containerId).innerHTML = items.map(function (i) {
            return '<div class="stat"><span class="stat-value' + (i.cls ? " " + i.cls : "") + '">' + esc(i.value) +
                '</span><span class="stat-label">' + esc(i.label) + "</span></div>";
        }).join("");
    }

    // ------------------------------------------------------------------ datos compartidos
    function loadPlans() {
        return QA.api.get("/api/v1/plans").then(function (plans) {
            state.plans = plans;
            var options = plans.map(function (p) { return { value: String(p.id), label: p.code + " · " + p.name }; });
            ["case-filter-plan", "case-plan", "rtm-plan", "req-plan"].forEach(function (id) { QA.fillSelect($(id), options); });
            renderPlans();
            return plans;
        });
    }

    function loadRequirements() {
        return QA.api.get("/api/v1/requirements").then(function (reqs) {
            state.requirements = reqs;
            QA.fillSelect($("case-filter-requirement"), reqs.map(function (r) {
                return { value: String(r.id), label: r.code + " · " + r.title };
            }));
            return reqs;
        });
    }

    // ================================================================== PLAN DE PRUEBAS
    var PLAN_FIELDS = { name: "plan-name", version: "plan-version", status: "plan-status", responsible: "plan-responsible",
        environment: "plan-environment", start_date: "plan-start", end_date: "plan-end", objective: "plan-objective",
        scope_in: "plan-scope-in", scope_out: "plan-scope-out", features: "plan-features", approach: "plan-approach",
        acceptance_criteria: "plan-acceptance", resources: "plan-resources", schedule: "plan-schedule", risks: "plan-risks" };

    function renderPlans() {
        var list = $("plan-list");
        if (!state.plans.length) {
            list.innerHTML = '<div class="panel empty-state"><h3>Aún no hay planes de prueba</h3>' +
                '<p class="muted">Crea el plan con el alcance, las funciones a evaluar, los criterios de aceptación, los recursos y el cronograma.</p></div>';
            return;
        }
        list.innerHTML = state.plans.map(function (p) {
            var s = p.summary;
            return '<article class="panel plan-card" data-plan-id="' + p.id + '">' +
                '<div class="plan-head"><div><p class="muted small">' + esc(p.code) + " · v" + esc(p.version) + " · " + esc(p.environment) +
                "</p><h3>" + esc(p.name) + '</h3></div><span class="pill ' + (p.status === "Cerrado" ? "" : p.status === "Aprobado" || p.status === "En ejecución" ? "pill-success" : "st-new") + '">' + esc(p.status) + "</span></div>" +
                '<p class="muted small">' + esc([p.responsible ? "Responsable: " + p.responsible : "", (p.start_date || p.end_date) ? (p.start_date || "?") + " → " + (p.end_date || "?") : ""].filter(Boolean).join(" · ")) + "</p>" +
                (p.objective ? '<p class="plan-objective">' + esc(p.objective) + "</p>" : "") +
                '<div class="plan-metrics">' +
                "<div><span>Casos ejecutados</span><strong>" + s.executed + "/" + s.cases + "</strong>" + bar(s.execution_rate, "progress-info") + "</div>" +
                "<div><span>Pass rate</span><strong>" + QA.fmt(s.pass_rate, 1) + " %</strong>" + bar(s.pass_rate) + "</div>" +
                "<div><span>Cobertura de requisitos</span><strong>" + s.covered + "/" + s.requirements + "</strong>" + bar(s.coverage, "progress-warning") + "</div>" +
                "<div><span>Fallidos / bloqueados</span><strong>" + s.by_status["Fallido"] + " / " + s.by_status["Bloqueado"] + "</strong></div>" +
                "</div>" +
                '<div class="row-actions plan-actions">' +
                '<button type="button" class="btn-mini" data-act="cases">Casos</button>' +
                '<button type="button" class="btn-mini" data-act="rtm">Trazabilidad</button>' +
                '<button type="button" class="btn-mini" data-act="pdf">PDF</button>' +
                '<button type="button" class="btn-mini" data-act="excel">Excel</button>' +
                '<button type="button" class="btn-mini" data-act="edit">Editar</button>' +
                '<button type="button" class="btn-mini btn-mini-danger" data-act="delete">Eliminar</button>' +
                "</div></article>";
        }).join("");
    }

    function openPlanForm(plan) {
        $("form-plan").reset();
        QA.setMsg("plan-msg", "");
        $("plan-id").value = plan ? plan.id : "";
        $("dlg-plan-title").textContent = plan ? "Editar " + plan.code : "Nuevo plan de pruebas";
        Object.keys(PLAN_FIELDS).forEach(function (key) {
            var defaults = { version: "1.0", status: "Borrador", environment: "QA" };
            $(PLAN_FIELDS[key]).value = plan ? (plan[key] || "") : (defaults[key] || "");
        });
        if (!plan) { $("plan-responsible").value = (window.QAAuth.getUser() || {}).name || ""; }
        QA.openDialog("dlg-plan");
        $("plan-name").focus();
    }

    function savePlan(event) {
        event.preventDefault();
        var payload = {};
        Object.keys(PLAN_FIELDS).forEach(function (key) { payload[key] = $(PLAN_FIELDS[key]).value.trim(); });
        if (!payload.name) { QA.setMsg("plan-msg", "El nombre del plan es obligatorio.", "error"); return; }
        var id = $("plan-id").value;
        var button = $("btn-plan-save");
        QA.setLoading(button, true);
        (id ? QA.api.put("/api/v1/plans/" + id, payload) : QA.api.post("/api/v1/plans", payload))
            .then(function (plan) {
                QA.closeDialog("dlg-plan");
                QA.toast("Plan " + plan.code + (id ? " actualizado" : " creado"), "success");
                QA.emit("docs-changed");
            })
            .catch(function (err) { QA.handleError(err, "plan-msg"); })
            .then(function () { QA.setLoading(button, false); });
    }

    function onPlanClick(event) {
        var button = event.target.closest("button[data-act]");
        if (!button) { return; }
        var id = Number(button.closest("[data-plan-id]").dataset.planId);
        var plan = state.plans.filter(function (p) { return p.id === id; })[0];
        var act = button.dataset.act;
        if (act === "edit") { openPlanForm(plan); }
        if (act === "pdf" || act === "excel") { download("/api/v1/plans/" + id + "/report?format=" + act); }
        if (act === "cases") { $("case-filter-plan").value = String(id); QA.go("casos"); loadCases(); }
        if (act === "rtm") { $("rtm-plan").value = String(id); QA.go("trazabilidad"); loadRtm(); }
        if (act === "delete") {
            QA.confirm("¿Eliminar el plan " + plan.code + "? Sus casos y requisitos se conservan sin plan.").then(function (ok) {
                if (!ok) { return; }
                return QA.api.del("/api/v1/plans/" + id).then(function () {
                    QA.toast("Plan eliminado", "success");
                    QA.emit("docs-changed");
                });
            }).catch(function (err) { QA.handleError(err); });
        }
    }

    // ================================================================== CASOS DE PRUEBA
    var CASE_FIELDS = { title: "case-title", description: "case-description", plan_id: "case-plan", module: "case-module",
        type: "case-type", priority: "case-priority", tool: "case-tool", environment: "case-environment", url: "case-url",
        preconditions: "case-preconditions", input_data: "case-input", steps: "case-steps", expected: "case-expected",
        actual: "case-actual", status: "case-status", evidence_notes: "case-evidence-notes" };

    function caseFilters() {
        return { q: $("case-search").value.trim(), plan_id: $("case-filter-plan").value, status: $("case-filter-status").value,
            type: $("case-filter-type").value, requirement_id: $("case-filter-requirement").value };
    }

    function loadCases() {
        return QA.api.get("/api/v1/test-cases?" + query(caseFilters())).then(function (cases) {
            state.cases = cases;
            renderCases();
        }).catch(function (err) { QA.handleError(err); });
    }

    function renderCases() {
        var counts = {};
        state.cases.forEach(function (c) { counts[c.status] = (counts[c.status] || 0) + 1; });
        stats("case-stats", [{ label: "Casos", value: state.cases.length },
            { label: "Aprobados", value: counts["Aprobado"] || 0, cls: "ok" },
            { label: "Fallidos", value: counts["Fallido"] || 0, cls: "bad" },
            { label: "Bloqueados", value: counts["Bloqueado"] || 0, cls: "warn" },
            { label: "Sin ejecutar", value: counts["No ejecutado"] || 0 }]);
        var tbody = $("table-cases").querySelector("tbody");
        if (!state.cases.length) {
            tbody.innerHTML = '<tr><td colspan="9" class="empty">No hay casos de prueba con estos filtros.</td></tr>';
            return;
        }
        tbody.innerHTML = state.cases.map(function (c) {
            return '<tr data-case-id="' + c.id + '">' +
                "<td>" + esc(c.code) + "</td>" +
                '<td class="cell-title"><a href="#casos" class="cell-main" data-act="view">' + esc(c.title) + "</a>" +
                '<span class="cell-sub">' + esc([c.plan_code, c.module, c.tool].filter(Boolean).join(" · ")) + "</span></td>" +
                "<td>" + (c.requirements.map(function (r) { return '<span class="chip" title="' + esc(r.title) + '">' + esc(r.code) + "</span>"; }).join(" ") || '<span class="muted">—</span>') + "</td>" +
                "<td>" + esc(c.type) + "</td>" +
                "<td>" + esc(c.priority) + "</td>" +
                "<td>" + casePill(c.status) + (c.executed_at ? '<span class="cell-sub">' + esc(c.executed_at.slice(0, 16)) + "</span>" : "") + "</td>" +
                '<td class="num">' + (c.evidence_count || "—") + "</td>" +
                "<td>" + (c.incident_code ? '<a href="#novedades/' + c.incident_id + '">' + esc(c.incident_code) + "</a>" : "—") + "</td>" +
                '<td class="actions-col"><div class="row-actions">' +
                '<button type="button" class="btn-mini btn-mini-primary" data-act="execute">Ejecutar</button>' +
                '<button type="button" class="btn-mini" data-act="edit">Editar</button>' +
                '<button type="button" class="btn-mini" data-act="duplicate">Duplicar</button>' +
                '<button type="button" class="btn-mini btn-mini-danger" data-act="delete">Eliminar</button>' +
                "</div></td></tr>";
        }).join("");
    }

    function renderRequirementPicker(selected) {
        var box = $("case-requirements");
        if (!state.requirements.length) {
            box.innerHTML = '<span class="muted small">No hay requisitos. Créalos en «Matriz de trazabilidad».</span>';
            return;
        }
        var chosen = (selected || []).map(String);
        box.innerHTML = state.requirements.map(function (r) {
            return '<label class="check req-option"><input type="checkbox" value="' + r.id + '"' +
                (chosen.indexOf(String(r.id)) >= 0 ? " checked" : "") + "> <strong>" + esc(r.code) + "</strong> " + esc(r.title) + "</label>";
        }).join("");
    }

    function openCaseForm(spec) {
        $("form-case").reset();
        QA.setMsg("case-msg", "");
        $("case-id").value = spec ? spec.id : "";
        $("dlg-case-title").textContent = spec ? "Editar " + spec.code : "Nuevo caso de prueba";
        var defaults = { type: "Funcional", priority: "Normal", tool: "Manual", environment: "QA", status: "No ejecutado",
            plan_id: $("case-filter-plan").value };
        Object.keys(CASE_FIELDS).forEach(function (key) {
            var value = spec ? spec[key] : defaults[key];
            $(CASE_FIELDS[key]).value = value == null ? "" : String(value);
        });
        renderRequirementPicker(spec ? spec.requirements.map(function (r) { return r.id; }) : []);
        QA.openDialog("dlg-case");
        $("case-title").focus();
    }

    function saveCase(event) {
        event.preventDefault();
        var payload = {};
        Object.keys(CASE_FIELDS).forEach(function (key) { payload[key] = $(CASE_FIELDS[key]).value.trim(); });
        payload.plan_id = payload.plan_id || null;
        payload.requirement_ids = Array.prototype.map.call(document.querySelectorAll("#case-requirements input:checked"),
            function (c) { return Number(c.value); });
        if (!payload.title) { QA.setMsg("case-msg", "Describe qué se prueba en el caso.", "error"); return; }
        var id = $("case-id").value;
        var button = $("btn-case-save");
        QA.setLoading(button, true);
        (id ? QA.api.put("/api/v1/test-cases/" + id, payload) : QA.api.post("/api/v1/test-cases", payload))
            .then(function (spec) {
                QA.closeDialog("dlg-case");
                QA.toast("Caso " + spec.code + (id ? " actualizado" : " creado"), "success");
                QA.emit("docs-changed");
            })
            .catch(function (err) { QA.handleError(err, "case-msg"); })
            .then(function () { QA.setLoading(button, false); });
    }

    function fieldsHtml(pairs) {
        return pairs.filter(function (p) { return p[1]; }).map(function (p) {
            return "<dt>" + esc(p[0]) + "</dt><dd>" + (p[2] ? p[1] : esc(p[1])) + "</dd>";
        }).join("");
    }

    // ---------- ejecución
    function openExecute(spec) {
        state.execId = spec.id;
        $("form-execute").reset();
        QA.setMsg("exec-msg", "");
        $("exec-code").textContent = spec.code + (spec.plan_code ? " · " + spec.plan_code : "");
        $("dlg-execute-title").textContent = spec.title;
        $("exec-info").innerHTML = fieldsHtml([["Precondiciones", spec.preconditions], ["Datos de entrada", spec.input_data],
            ["Pasos", spec.steps], ["Resultado esperado", spec.expected], ["URL", spec.url]]) ||
            "<dt>Pasos</dt><dd class='muted'>El caso no tiene pasos definidos.</dd>";
        $("exec-severity").value = "Media";
        $("exec-priority").value = "Normal";
        $("exec-developer").value = "";
        toggleDefectBox();
        QA.openDialog("dlg-execute");
    }

    function execStatus() {
        var checked = document.querySelector("input[name='exec-status']:checked");
        return checked ? checked.value : "Aprobado";
    }

    function toggleDefectBox() {
        $("exec-defect").hidden = execStatus() !== "Fallido";
    }

    function uploadFiles(specId, input) {
        if (!input.files.length) { return Promise.resolve([]); }
        var data = new FormData();
        Array.prototype.forEach.call(input.files, function (f) { data.append("file", f); });
        return QA.api.upload("/api/v1/test-cases/" + specId + "/evidence", data);
    }

    function saveExecution(event) {
        event.preventDefault();
        var status = execStatus();
        var payload = { status: status, actual: $("exec-actual").value.trim(), evidence_notes: $("exec-notes").value.trim() };
        if (status === "Fallido") {
            if (!payload.actual) { QA.setMsg("exec-msg", "Describe el resultado obtenido para el reporte de defecto.", "error"); return; }
            payload.create_defect = $("exec-create-defect").checked;
            payload.severity = $("exec-severity").value;
            payload.priority = $("exec-priority").value;
            payload.developer_id = $("exec-developer").value || null;
        }
        var button = $("btn-exec-save");
        QA.setLoading(button, true);
        var id = state.execId;
        uploadFiles(id, $("exec-files"))
            .then(function () { return QA.api.post("/api/v1/test-cases/" + id + "/execute", payload); })
            .then(function (res) {
                QA.closeDialog("dlg-execute");
                QA.toast(res.code + ": " + res.status + (res.defect ? " · defecto " + res.defect.code + " enviado a Novedades" : ""),
                    res.status === "Fallido" ? "error" : "success");
                QA.emit("docs-changed");
                QA.emit("incidents-changed");
                QA.emit("data-changed");
            })
            .catch(function (err) { QA.handleError(err, "exec-msg"); })
            .then(function () { QA.setLoading(button, false); });
    }

    // ---------- detalle
    function openDetail(id) {
        return QA.api.get("/api/v1/test-cases/" + id).then(function (spec) {
            state.detail = spec;
            $("cd-code").textContent = spec.code + (spec.plan_code ? " · " + spec.plan_code + " " + spec.plan_name : "");
            $("cd-title").textContent = spec.title;
            $("cd-pills").innerHTML = casePill(spec.status) + '<span class="pill">' + esc(spec.type) + '</span><span class="pill">Prioridad ' +
                esc(spec.priority) + '</span><span class="pill">' + esc(spec.tool) + "</span>" +
                spec.requirements.map(function (r) { return '<span class="chip">' + esc(r.code) + "</span>"; }).join("");
            $("cd-fields").innerHTML = fieldsHtml([
                ["Propósito", spec.description], ["Módulo", spec.module], ["Ambiente / URL", spec.environment + (spec.url ? " · " + spec.url : "")],
                ["Precondiciones", spec.preconditions], ["Datos de entrada", spec.input_data], ["Pasos a seguir", spec.steps],
                ["Resultado esperado", spec.expected], ["Resultado obtenido", spec.actual],
                ["Ejecutado", spec.executed_at ? spec.executed_by + " · " + spec.executed_at : ""],
                ["Defecto", spec.incident_code ? '<a href="#novedades/' + spec.incident_id + '">' + esc(spec.incident_code) + "</a> (" + esc(spec.incident_status) + ")" : "", true],
                ["Logs / notas", spec.evidence_notes]]);
            renderEvidence(spec.evidence);
            $("cd-executions").innerHTML = spec.executions.length ? spec.executions.map(function (x) {
                return '<li class="tl-' + (x.status === "Fallido" ? "reaparicion" : x.status === "Aprobado" ? "notificacion" : "cambio") + '">' +
                    '<span class="tl-head"><strong>' + esc(x.status) + "</strong> · " + esc(x.executed_by) + " · " + esc(x.executed_at) +
                    (x.incident_code ? " · " + esc(x.incident_code) : "") + '</span><span class="tl-body">' + esc(x.actual || "—") + "</span></li>";
            }).join("") : '<li class="muted small">Aún no se ha ejecutado.</li>';
            QA.openDialog("dlg-case-detail");
        }).catch(function (err) { QA.handleError(err); });
    }

    function renderEvidence(list) {
        var box = $("cd-evidence");
        if (!list.length) { box.innerHTML = '<p class="muted small">Sin evidencias adjuntas.</p>'; return; }
        box.innerHTML = list.map(function (ev) {
            var isImage = /^image\//.test(ev.mimetype);
            return '<figure class="evidence" data-ev-id="' + ev.id + '">' +
                (isImage ? '<img alt="' + esc(ev.filename) + '" data-src="/api/v1/evidence/' + ev.id + '?inline=1">' : '<div class="evidence-file">' + esc(ev.filename.split(".").pop().toUpperCase()) + "</div>") +
                '<figcaption title="' + esc(ev.filename) + '">' + esc(ev.filename) + "</figcaption>" +
                '<div class="row-actions"><button type="button" class="btn-mini" data-act="download">Descargar</button>' +
                '<button type="button" class="btn-mini btn-mini-danger" data-act="delete">Quitar</button></div></figure>';
        }).join("");
        box.querySelectorAll("img[data-src]").forEach(function (img) {
            QA.api.fetch(img.dataset.src).then(function (r) { return r.ok ? r.blob() : null; }).then(function (blob) {
                if (blob) { img.src = URL.createObjectURL(blob); }
            }).catch(function () { /* opcional */ });
        });
    }

    function onEvidenceClick(event) {
        var button = event.target.closest("button[data-act]");
        if (!button) { return; }
        var id = button.closest("[data-ev-id]").dataset.evId;
        if (button.dataset.act === "download") { download("/api/v1/evidence/" + id); }
        if (button.dataset.act === "delete") {
            QA.confirm("¿Quitar esta evidencia?", "Quitar").then(function (ok) {
                if (!ok) { return; }
                return QA.api.del("/api/v1/evidence/" + id).then(function () {
                    QA.emit("docs-changed");
                    return openDetail(state.detail.id);
                });
            }).catch(function (err) { QA.handleError(err); });
        }
    }

    function onCaseClick(event) {
        var el = event.target.closest("[data-act]");
        if (!el) { return; }
        event.preventDefault();
        var id = Number(el.closest("tr").dataset.caseId);
        var spec = state.cases.filter(function (c) { return c.id === id; })[0];
        var act = el.dataset.act;
        if (act === "view") { openDetail(id); }
        if (act === "execute") { openExecute(spec); }
        if (act === "edit") { openCaseForm(spec); }
        if (act === "duplicate") {
            QA.api.post("/api/v1/test-cases/" + id + "/duplicate").then(function (copy) {
                QA.toast("Caso duplicado como " + copy.code, "success");
                QA.emit("docs-changed");
            }).catch(function (err) { QA.handleError(err); });
        }
        if (act === "delete") {
            QA.confirm("¿Eliminar el caso " + spec.code + " con sus evidencias e historial de ejecuciones?").then(function (ok) {
                if (!ok) { return; }
                return QA.api.del("/api/v1/test-cases/" + id).then(function () {
                    QA.toast("Caso " + spec.code + " eliminado", "success");
                    QA.emit("docs-changed");
                });
            }).catch(function (err) { QA.handleError(err); });
        }
    }

    // ================================================================== MATRIZ DE TRAZABILIDAD
    var REQ_FIELDS = { code: "req-code", kind: "req-kind", title: "req-title", description: "req-description",
        priority: "req-priority", module: "req-module", plan_id: "req-plan" };

    function loadRtm() {
        var planId = $("rtm-plan").value;
        return QA.api.get("/api/v1/rtm" + (planId ? "?plan_id=" + planId : "")).then(renderRtm)
            .catch(function (err) { QA.handleError(err); });
    }

    function renderRtm(rtm) {
        var t = rtm.totals;
        var by = t.by_coverage || {};
        stats("rtm-stats", [{ label: "Requisitos", value: t.requirements }, { label: "Con casos", value: t.covered },
            { label: "Cobertura", value: QA.fmt(t.coverage, 1) + " %", cls: t.coverage >= 100 ? "ok" : "warn" },
            { label: "Validados", value: by["Validado"] || 0, cls: "ok" }, { label: "Con fallas", value: by["Con fallas"] || 0, cls: "bad" },
            { label: "Sin cobertura", value: by["Sin cobertura"] || 0, cls: "bad" }]);
        var tbody = $("table-rtm").querySelector("tbody");
        tbody.innerHTML = rtm.rows.length ? rtm.rows.map(function (r) {
            return '<tr data-req-id="' + r.id + '">' +
                '<td><span class="cell-main">' + esc(r.code) + '</span><span class="cell-sub">' + esc(r.kind) + " · " + esc(r.priority) + "</span></td>" +
                '<td><span class="cell-main">' + esc(r.title) + "</span>" + (r.module ? '<span class="cell-sub">' + esc(r.module) + "</span>" : "") + "</td>" +
                "<td>" + (r.cases.map(function (c) {
                    return '<span class="chip chip-' + esc(c.status.toLowerCase().replace(/\s+/g, "-")) + '" title="' + esc(c.title + " — " + c.status) + '">' + esc(c.code) + "</span>";
                }).join(" ") || '<span class="muted">Sin casos</span>') + "</td>" +
                "<td>" + (r.defects.map(esc).join(", ") || "—") + "</td>" +
                "<td>" + coveragePill(r.coverage) + "</td>" +
                '<td class="actions-col"><div class="row-actions">' +
                '<button type="button" class="btn-mini" data-act="new-case">+ Caso</button>' +
                '<button type="button" class="btn-mini" data-act="edit">Editar</button>' +
                '<button type="button" class="btn-mini btn-mini-danger" data-act="delete">Eliminar</button>' +
                "</div></td></tr>";
        }).join("") : '<tr><td colspan="6" class="empty">Registra los requisitos o historias de usuario del cliente para medir la cobertura.</td></tr>';
        var orphans = $("rtm-orphans");
        orphans.hidden = !rtm.orphan_cases.length;
        orphans.innerHTML = '<p class="small"><strong>Casos sin requisito asociado (' + rtm.orphan_cases.length + "):</strong> " +
            rtm.orphan_cases.map(function (c) { return '<span class="chip">' + esc(c.code) + "</span> " + esc(c.title); }).join(" · ") + "</p>";
    }

    function resetReqForm() {
        $("form-requirement").reset();
        $("req-id").value = "";
        $("req-plan").value = $("rtm-plan").value;
        $("req-form-title").textContent = "Nuevo requisito";
        $("btn-req-cancel").hidden = true;
    }

    function saveRequirement(event) {
        event.preventDefault();
        var payload = {};
        Object.keys(REQ_FIELDS).forEach(function (key) { payload[key] = $(REQ_FIELDS[key]).value.trim(); });
        payload.plan_id = payload.plan_id || null;
        if (!payload.title) { QA.setMsg("req-msg", "El título es obligatorio.", "error"); return; }
        var id = $("req-id").value;
        var button = $("btn-req-save");
        QA.setLoading(button, true);
        (id ? QA.api.put("/api/v1/requirements/" + id, payload) : QA.api.post("/api/v1/requirements", payload))
            .then(function (req) {
                QA.setMsg("req-msg", "Requisito " + req.code + (id ? " actualizado." : " registrado."), "success");
                resetReqForm();
                QA.emit("docs-changed");
            })
            .catch(function (err) { QA.handleError(err, "req-msg"); })
            .then(function () { QA.setLoading(button, false); });
    }

    function onRtmClick(event) {
        var button = event.target.closest("button[data-act]");
        if (!button) { return; }
        var id = Number(button.closest("tr").dataset.reqId);
        var req = state.requirements.filter(function (r) { return r.id === id; })[0];
        if (!req) { return; }
        if (button.dataset.act === "edit") {
            Object.keys(REQ_FIELDS).forEach(function (key) { $(REQ_FIELDS[key]).value = req[key] == null ? "" : String(req[key]); });
            $("req-id").value = req.id;
            $("req-form-title").textContent = "Editar " + req.code;
            $("btn-req-cancel").hidden = false;
            QA.setMsg("req-msg", "");
            $("req-title").focus();
        }
        if (button.dataset.act === "new-case") {
            openCaseForm(null);
            $("case-plan").value = req.plan_id ? String(req.plan_id) : "";
            $("case-module").value = req.module || "";
            renderRequirementPicker([req.id]);
        }
        if (button.dataset.act === "delete") {
            QA.confirm("¿Eliminar el requisito " + req.code + "? Los casos se conservan pero pierden el vínculo.").then(function (ok) {
                if (!ok) { return; }
                return QA.api.del("/api/v1/requirements/" + id).then(function () {
                    QA.toast("Requisito eliminado", "success");
                    QA.emit("docs-changed");
                });
            }).catch(function (err) { QA.handleError(err); });
        }
    }

    // ================================================================== REPORTE DE DEFECTOS
    var IMPACT = { "Crítica": "Bloquea una función principal o provoca pérdida de datos.",
        "Alta": "Afecta una función importante; alternativa difícil.", "Media": "Afecta una función secundaria o hay alternativa.",
        "Baja": "Detalle visual o de usabilidad." };

    function defectFilters() {
        return { open: $("defect-filter-open").value, severity: $("defect-filter-severity").value,
            developer_id: $("defect-filter-developer").value, source: $("defect-filter-source").value };
    }

    function loadDefects() {
        return QA.api.get("/api/v1/incidents?" + query(Object.assign({ order: "severity" }, defectFilters())))
            .then(renderDefects).catch(function (err) { QA.handleError(err); });
    }

    function renderDefects(list) {
        var sev = { "Crítica": 0, "Alta": 0, "Media": 0, "Baja": 0 };
        list.forEach(function (i) { sev[i.severity] = (sev[i.severity] || 0) + 1; });
        stats("defect-stats", [{ label: "Defectos", value: list.length }, { label: "Críticos", value: sev["Crítica"], cls: "bad" },
            { label: "Altos", value: sev["Alta"], cls: "bad" }, { label: "Medios", value: sev["Media"], cls: "warn" },
            { label: "Bajos", value: sev["Baja"] }]);
        $("defect-list").innerHTML = list.length ? list.map(function (i) {
            return '<article class="defect-card" data-incident-id="' + i.id + '">' +
                '<div class="plan-head"><div><p class="muted small">' + esc(i.code) + " · " + esc(i.source) + (i.source_ref ? " " + esc(i.source_ref) : "") +
                " · " + esc(i.created_at.slice(0, 16)) + "</p><h3>" + esc(i.title) + "</h3></div>" +
                '<div class="pill-row tight">' + QA.severityPill(i.severity) + QA.statusPill(i.status) + "</div></div>" +
                '<dl class="detail-fields compact">' + fieldsHtml([
                    ["Impacto", IMPACT[i.severity]], ["Asignado a", i.developer_name || "Sin asignar"],
                    ["Módulo / ambiente", [i.module, i.environment].filter(Boolean).join(" · ")], ["URL", i.url],
                    ["Pasos para reproducir", i.steps], ["Resultado esperado", i.expected], ["Resultado obtenido", i.actual]]) + "</dl>" +
                '<div class="row-actions"><a class="btn-mini" href="#novedades/' + i.id + '">Gestionar / enviar</a>' +
                '<button type="button" class="btn-mini" data-act="pdf">PDF</button>' +
                '<button type="button" class="btn-mini" data-act="excel">Excel</button></div></article>';
        }).join("") : '<p class="empty">No hay defectos con estos filtros.</p>';
    }

    // ================================================================== Resumen y reportes
    function renderDocsProgress(docs) {
        if (!docs) { return; }
        $("docs-execution").textContent = docs.executed + "/" + docs.cases + " (" + QA.fmt(docs.execution_rate, 1) + " %)";
        $("docs-execution-bar").style.width = Math.min(100, docs.execution_rate) + "%";
        $("docs-pass").textContent = QA.fmt(docs.pass_rate, 1) + " %";
        $("docs-pass-bar").style.width = Math.min(100, docs.pass_rate) + "%";
        $("docs-coverage").textContent = docs.covered + "/" + docs.requirements + " (" + QA.fmt(docs.coverage, 1) + " %)";
        $("docs-coverage-bar").style.width = Math.min(100, docs.coverage) + "%";
        $("docs-statuses").innerHTML = Object.keys(docs.by_status).map(function (k) {
            return '<span class="pill ' + (CASE_STATUS_CLASS[k] || "") + '">' + esc(k) + ": " + docs.by_status[k] + "</span>";
        }).join("");
    }

    function loadAutoReports() {
        QA.api.get("/api/v1/reports/auto").then(function (data) {
            $("auto-report-info").textContent = data.report_hour !== ""
                ? "Se genera solo todos los días a las " + data.report_hour + ":00" +
                  (data.report_recipients ? " y se envía a " + data.report_recipients : " (sin destinatarios de correo)") +
                  ". Último: " + (data.last_date || "nunca") + ". Configúralo en «Configuración»."
                : "El reporte diario está desactivado. Actívalo en «Configuración».";
            $("auto-report-list").innerHTML = data.reports.length ? data.reports.slice(0, 20).map(function (r) {
                return '<li data-name="' + esc(r.name) + '"><span class="badge ' + (r.name.slice(-3) === "pdf" ? "badge-pdf" : "badge-excel") + '">' +
                    (r.name.slice(-3) === "pdf" ? "PDF" : "XLSX") + "</span> <span>" + esc(r.created_at) + '</span><span class="muted small">' +
                    QA.fmt(r.size / 1024) + " KB</span>" +
                    '<button type="button" class="btn-mini" data-act="download">Descargar</button>' +
                    '<button type="button" class="btn-mini btn-mini-danger" data-act="delete">Eliminar</button></li>';
            }).join("") : '<li class="muted small">Aún no hay reportes generados.</li>';
        }).catch(function (err) { QA.handleError(err, "auto-report-msg"); });
    }

    function generateAutoReport() {
        var button = $("btn-auto-report");
        QA.setLoading(button, true, "Generando");
        QA.api.post("/api/v1/reports/auto").then(function (res) {
            QA.setMsg("auto-report-msg", "Generado: " + res.files.join(", ") +
                (res.emailed_to ? ". Enviado a " + res.emailed_to : res.email_error ? ". Correo no enviado: " + res.email_error : ""),
                res.email_error ? "error" : "success");
            loadAutoReports();
        }).catch(function (err) { QA.handleError(err, "auto-report-msg"); })
            .then(function () { QA.setLoading(button, false, "Generar ahora"); });
    }

    // ================================================================== init
    function refreshAll() {
        var route = QA.route().view;
        Promise.all([loadPlans(), loadRequirements()]).then(function () {
            if (route === "casos") { loadCases(); }
            if (route === "trazabilidad") { loadRtm(); }
        }).catch(function (err) { QA.handleError(err); });
        QA.emit("data-changed");
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (!window.QAAuth.getToken()) { return; }

        QA.api.get("/api/v1/docs/catalogs").then(function (c) {
            state.catalogs = c;
            QA.fillSelect($("plan-status"), c.plan_statuses);
            QA.fillSelect($("plan-environment"), c.environments);
            QA.fillSelect($("case-type"), c.case_types);
            QA.fillSelect($("case-priority"), c.priorities);
            QA.fillSelect($("case-tool"), c.tools);
            QA.fillSelect($("case-environment"), c.environments);
            QA.fillSelect($("case-status"), c.case_statuses);
            QA.fillSelect($("case-filter-status"), c.case_statuses);
            QA.fillSelect($("case-filter-type"), c.case_types);
            QA.fillSelect($("req-kind"), c.requirement_kinds);
            QA.fillSelect($("req-priority"), c.priorities, { value: "Normal" });
            QA.fillSelect($("exec-severity"), c.severities, { value: "Media" });
            QA.fillSelect($("exec-priority"), c.priorities, { value: "Normal" });
            QA.fillSelect($("defect-filter-severity"), c.severities);
        }).catch(function (err) { QA.handleError(err); });
        QA.on("catalogs", function (c) { QA.fillSelect($("defect-filter-source"), c.incident_sources); });
        QA.on("developers", function () {
            QA.fillSelect($("exec-developer"), QA.developerOptions(true));
            QA.fillSelect($("defect-filter-developer"), [{ value: "none", label: "Sin asignar" }].concat(QA.developerOptions(false)));
        });
        loadPlans().catch(function () {});
        loadRequirements().catch(function () {});

        QA.on("view:plan", function () { loadPlans(); });
        QA.on("view:casos", function () { loadRequirements().then(loadCases); });
        QA.on("view:trazabilidad", function () { loadRequirements().then(loadRtm); resetReqForm(); });
        QA.on("view:defectos", loadDefects);
        QA.on("view:reportes", loadAutoReports);
        QA.on("docs-changed", refreshAll);
        QA.on("incidents-changed", function () { if (QA.route().view === "defectos") { loadDefects(); } });
        QA.on("metrics", function (data) { renderDocsProgress(data.docs); });

        // Plan
        $("btn-new-plan").addEventListener("click", function () { openPlanForm(null); });
        $("form-plan").addEventListener("submit", savePlan);
        $("plan-list").addEventListener("click", onPlanClick);

        // Casos
        $("btn-new-case").addEventListener("click", function () { openCaseForm(null); });
        $("form-case").addEventListener("submit", saveCase);
        $("table-cases").addEventListener("click", onCaseClick);
        var timer;
        $("case-search").addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(loadCases, 250); });
        ["case-filter-plan", "case-filter-status", "case-filter-type", "case-filter-requirement"].forEach(function (id) {
            $(id).addEventListener("change", loadCases);
        });
        $("btn-cases-pdf").addEventListener("click", function () {
            download("/api/v1/test-cases/report?" + query(Object.assign({ format: "pdf" }, caseFilters())));
        });
        $("btn-cases-excel").addEventListener("click", function () {
            download("/api/v1/test-cases/report?" + query(Object.assign({ format: "excel" }, caseFilters())));
        });
        $("form-execute").addEventListener("submit", saveExecution);
        document.querySelectorAll("input[name='exec-status']").forEach(function (r) { r.addEventListener("change", toggleDefectBox); });
        $("cd-evidence").addEventListener("click", onEvidenceClick);
        $("form-cd-upload").addEventListener("submit", function (event) {
            event.preventDefault();
            uploadFiles(state.detail.id, $("cd-files")).then(function (saved) {
                if (saved.length) { QA.toast(saved.length + " evidencia(s) adjuntada(s)", "success"); }
                QA.emit("docs-changed");
                return openDetail(state.detail.id);
            }).catch(function (err) { QA.handleError(err); });
        });
        $("btn-cd-pdf").addEventListener("click", function () { download("/api/v1/test-cases/" + state.detail.id + "/report?format=pdf"); });
        $("btn-cd-excel").addEventListener("click", function () { download("/api/v1/test-cases/" + state.detail.id + "/report?format=excel"); });
        $("btn-cd-edit").addEventListener("click", function () {
            var spec = state.detail;
            QA.closeDialog("dlg-case-detail");
            openCaseForm(spec);
        });
        $("btn-cd-execute").addEventListener("click", function () {
            var spec = state.detail;
            QA.closeDialog("dlg-case-detail");
            openExecute(spec);
        });

        // Trazabilidad
        $("form-requirement").addEventListener("submit", saveRequirement);
        $("btn-req-cancel").addEventListener("click", function () { resetReqForm(); QA.setMsg("req-msg", ""); });
        $("table-rtm").addEventListener("click", onRtmClick);
        $("rtm-plan").addEventListener("change", function () { loadRtm(); resetReqForm(); });
        $("btn-rtm-pdf").addEventListener("click", function () { download("/api/v1/rtm/report?" + query({ format: "pdf", plan_id: $("rtm-plan").value })); });
        $("btn-rtm-excel").addEventListener("click", function () { download("/api/v1/rtm/report?" + query({ format: "excel", plan_id: $("rtm-plan").value })); });

        // Defectos
        ["defect-filter-open", "defect-filter-severity", "defect-filter-developer", "defect-filter-source"].forEach(function (id) {
            $(id).addEventListener("change", loadDefects);
        });
        $("btn-defects-pdf").addEventListener("click", function () { download("/api/v1/defects/report?" + query(Object.assign({ format: "pdf" }, defectFilters()))); });
        $("btn-defects-excel").addEventListener("click", function () { download("/api/v1/defects/report?" + query(Object.assign({ format: "excel" }, defectFilters()))); });
        $("defect-list").addEventListener("click", function (event) {
            var button = event.target.closest("button[data-act]");
            if (!button) { return; }
            download("/api/v1/incidents/" + button.closest("[data-incident-id]").dataset.incidentId + "/report?format=" + button.dataset.act);
        });

        // Reportes
        document.querySelectorAll("[data-doc]").forEach(function (button) {
            button.addEventListener("click", function () {
                download(button.dataset.doc + "?format=" + button.dataset.format, "export-doc-status");
            });
        });
        $("btn-auto-report").addEventListener("click", generateAutoReport);
        $("auto-report-list").addEventListener("click", function (event) {
            var button = event.target.closest("button[data-act]");
            if (!button) { return; }
            var name = button.closest("li").dataset.name;
            if (button.dataset.act === "download") { download("/api/v1/reports/auto/" + encodeURIComponent(name)); }
            if (button.dataset.act === "delete") {
                QA.confirm("¿Eliminar el reporte " + name + "?").then(function (ok) {
                    if (!ok) { return; }
                    return QA.api.del("/api/v1/reports/auto/" + encodeURIComponent(name)).then(loadAutoReports);
                }).catch(function (err) { QA.handleError(err); });
            }
        });
        $("btn-scan-pdf").addEventListener("click", function () {
            var id = ($("scan-result-title").textContent || "").split(" ")[0];
            download("/api/v1/scans/" + id + "/report?format=pdf");
        });
        $("btn-scan-excel").addEventListener("click", function () {
            var id = ($("scan-result-title").textContent || "").split(" ")[0];
            download("/api/v1/scans/" + id + "/report?format=excel");
        });
    });
})();
