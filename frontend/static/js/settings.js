/**
 * Configuración: monitoreo, creación/envío automático de novedades, webhook y correo SMTP.
 */
(function () {
    "use strict";

    var QA = window.QA;
    var $ = QA.$;
    var CHECKBOXES = ["auto_incidents", "auto_incident_warnings", "auto_notify", "smtp_tls"];

    function fields() {
        return Array.prototype.slice.call($("form-settings").querySelectorAll("[name]"));
    }

    function loadSettings() {
        QA.api.get("/api/v1/settings").then(function (s) {
            fields().forEach(function (input) {
                if (input.type === "checkbox") {
                    input.checked = s[input.name] === "1";
                } else if (input.name === "smtp_password") {
                    input.value = "";
                    input.placeholder = s.smtp_password_set ? "•••••••• (guardada; vacío = no cambiar)" : "";
                } else {
                    input.value = s[input.name] || "";
                }
            });
            $("scan-wait").value = s.scan_wait_seconds || 2;
            $("scan-auto").checked = s.auto_incidents === "1";
        }).catch(function (err) { QA.handleError(err, "settings-msg"); });
    }

    function saveSettings(event) {
        if (event) { event.preventDefault(); }
        var payload = {};
        fields().forEach(function (input) {
            payload[input.name] = CHECKBOXES.indexOf(input.name) >= 0 ? (input.checked ? "1" : "0") : input.value.trim();
        });
        var button = $("btn-settings-save");
        QA.setLoading(button, true);
        return QA.api.put("/api/v1/settings", payload)
            .then(function () {
                QA.setMsg("settings-msg", "Configuración guardada.", "success");
                loadSettings();
            })
            .catch(function (err) { QA.handleError(err, "settings-msg"); throw err; })
            .then(function (r) { QA.setLoading(button, false); return r; }, function (err) { QA.setLoading(button, false); throw err; });
    }

    function testChannel(url, payload) {
        // Se guarda primero para probar con los datos que se ven en pantalla.
        saveSettings().then(function () {
            QA.setMsg("settings-msg", "Enviando prueba…", "info");
            return QA.api.post(url, payload || {});
        }).then(function (res) {
            QA.setMsg("settings-msg", res.message, "success");
        }).catch(function (err) { QA.handleError(err, "settings-msg"); });
    }

    document.addEventListener("DOMContentLoaded", function () {
        if (!window.QAAuth.getToken()) { return; }
        loadSettings();
        QA.on("view:configuracion", loadSettings);
        $("form-settings").addEventListener("submit", function (event) { saveSettings(event).catch(function () {}); });
        $("btn-test-webhook").addEventListener("click", function () { testChannel("/api/v1/settings/test-webhook"); });
        $("btn-test-email").addEventListener("click", function () {
            var to = $("set-test-email").value.trim();
            if (!to) {
                QA.setMsg("settings-msg", "Escribe el correo al que se enviará la prueba.", "error");
                return;
            }
            testChannel("/api/v1/settings/test-email", { to: to });
        });
    });
})();
