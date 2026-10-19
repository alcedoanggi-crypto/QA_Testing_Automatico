/**
 * Lógica de autenticación: login, almacenamiento del token JWT y logout.
 * Expone window.QAAuth para que otros scripts (dashboard.js) reutilicen la sesión.
 */
(function () {
    "use strict";

    var TOKEN_KEY = "qa_token";
    var USER_KEY = "qa_user";
    var LOGIN_URL = "/login";
    var DASHBOARD_URL = "/dashboard";
    var LOGIN_ENDPOINT = "/api/v1/auth/login";
    var EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    function safeGet(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }

    function getToken() {
        return safeGet(TOKEN_KEY);
    }

    function getUser() {
        try { return JSON.parse(safeGet(USER_KEY) || "null"); } catch (e) { return null; }
    }

    function setSession(token, user) {
        localStorage.setItem(TOKEN_KEY, token);
        localStorage.setItem(USER_KEY, JSON.stringify(user || {}));
    }

    function clearSession() {
        try {
            localStorage.removeItem(TOKEN_KEY);
            localStorage.removeItem(USER_KEY);
        } catch (e) { /* almacenamiento no disponible */ }
    }

    function logout() {
        clearSession();
        window.location.replace(LOGIN_URL);
    }

    window.QAAuth = {
        getToken: getToken,
        getUser: getUser,
        setSession: setSession,
        clearSession: clearSession,
        logout: logout
    };

    // ------------------------------------------------------------------ Login
    function initLoginForm(form) {
        var emailInput = document.getElementById("email");
        var passwordInput = document.getElementById("password");
        var submitBtn = document.getElementById("btn-login");
        var errorBox = document.getElementById("login-error-msg");
        var toggleBtn = document.getElementById("btn-toggle-password");

        function showError(message) {
            errorBox.textContent = message;
            errorBox.hidden = false;
        }

        function hideError() {
            errorBox.textContent = "";
            errorBox.hidden = true;
            emailInput.classList.remove("is-invalid");
            passwordInput.classList.remove("is-invalid");
        }

        function setLoading(isLoading) {
            submitBtn.disabled = isLoading;
            submitBtn.classList.toggle("is-loading", isLoading);
            submitBtn.querySelector(".btn-label").textContent = isLoading ? "Ingresando" : "Iniciar sesión";
        }

        if (toggleBtn) {
            toggleBtn.addEventListener("click", function () {
                var show = passwordInput.type === "password";
                passwordInput.type = show ? "text" : "password";
                toggleBtn.textContent = show ? "Ocultar" : "Mostrar";
                toggleBtn.setAttribute("aria-label", show ? "Ocultar contraseña" : "Mostrar contraseña");
            });
        }

        [emailInput, passwordInput].forEach(function (input) {
            input.addEventListener("input", hideError);
        });

        form.addEventListener("submit", function (event) {
            event.preventDefault();
            hideError();

            var email = emailInput.value.trim();
            var password = passwordInput.value;

            if (!email || !password) {
                if (!email) { emailInput.classList.add("is-invalid"); }
                if (!password) { passwordInput.classList.add("is-invalid"); }
                showError("Ingresa tu correo y contraseña.");
                return;
            }
            if (!EMAIL_PATTERN.test(email)) {
                emailInput.classList.add("is-invalid");
                showError("Ingresa un correo electrónico válido.");
                return;
            }

            setLoading(true);
            fetch(LOGIN_ENDPOINT, {
                method: "POST",
                headers: { "Content-Type": "application/json", "Accept": "application/json" },
                body: JSON.stringify({ email: email, password: password })
            })
                .then(function (response) {
                    return response.json().catch(function () { return {}; }).then(function (body) {
                        return { ok: response.ok, status: response.status, body: body };
                    });
                })
                .then(function (result) {
                    if (result.ok && result.body.token) {
                        setSession(result.body.token, result.body.user);
                        window.location.replace(DASHBOARD_URL);
                        return;
                    }
                    showError(result.body.error || "No fue posible iniciar sesión (HTTP " + result.status + ").");
                    passwordInput.value = "";
                    passwordInput.focus();
                    setLoading(false);
                })
                .catch(function () {
                    showError("No se pudo conectar con el servidor. Intenta nuevamente.");
                    setLoading(false);
                });
        });
    }

    // ------------------------------------------------------------------ Logout
    function initLogoutButton(button) {
        button.addEventListener("click", logout);
    }

    document.addEventListener("DOMContentLoaded", function () {
        var form = document.getElementById("login-form");
        if (form) { initLoginForm(form); }

        var logoutBtn = document.getElementById("btn-logout");
        if (logoutBtn) { initLogoutButton(logoutBtn); }
    });
})();
