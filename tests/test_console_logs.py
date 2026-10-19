"""Pruebas unitarias de consola y logs.

Ejecutar (desde la raíz del proyecto):
    python -m pytest tests/test_console_logs.py -v
    python -m unittest tests/test_console_logs.py -v
"""
import io
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

# Base de datos temporal: las pruebas no deben escribir en backend/data/qa_reports.db
os.environ.setdefault("QA_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="qa_reports_test_"), "qa_reports.db"))
BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import create_app  # noqa: E402
from logger import LOGGER_NAME  # noqa: E402

VALID_EMAIL = "admin@test.com"
VALID_PASSWORD = "SecurePassword123"
LOGIN_URL = "/api/v1/auth/login"

# [WARNING] [2026-10-19 09:00:00] INTENTO_FALLIDO_LOGIN - Email: admin@test.com | IP: 127.0.0.1
FAILED_LOGIN_PATTERN = re.compile(
    r"^\[WARNING\] \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] "
    r"INTENTO_FALLIDO_LOGIN - Email: (?P<email>\S+) \| IP: (?P<ip>\S+)$",
    re.MULTILINE,
)


class ConsoleLogsTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True

    def setUp(self):
        self.client = self.app.test_client()

    def _login_capturing_stdout(self, email, password):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            response = self.client.post(LOGIN_URL, json={"email": email, "password": password})
        return response, buffer.getvalue()

    def test_failed_login_writes_warning_to_console(self):
        response, output = self._login_capturing_stdout(VALID_EMAIL, "ContraseñaIncorrecta")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "Credenciales inválidas"})
        assert "[WARNING]" in output, f"No se encontró el nivel WARNING en consola: {output!r}"
        assert "INTENTO_FALLIDO_LOGIN" in output, f"No se encontró el tag INTENTO_FALLIDO_LOGIN: {output!r}"

    def test_failed_login_log_line_has_exact_format(self):
        _, output = self._login_capturing_stdout(VALID_EMAIL, "otra-clave-mala")

        match = FAILED_LOGIN_PATTERN.search(output)
        assert match is not None, f"La traza no respeta el formato esperado: {output!r}"
        self.assertEqual(match.group("email"), VALID_EMAIL)
        self.assertEqual(match.group("ip"), "127.0.0.1")

    def test_failed_login_with_unknown_user_is_logged(self):
        response, output = self._login_capturing_stdout("intruso@test.com", "123456")

        self.assertEqual(response.status_code, 401)
        self.assertIn("INTENTO_FALLIDO_LOGIN - Email: intruso@test.com | IP: 127.0.0.1", output)

    def test_failed_login_emits_warning_record_via_log_handler(self):
        with self.assertLogs(LOGGER_NAME, level="WARNING") as captured:
            self.client.post(LOGIN_URL, json={"email": VALID_EMAIL, "password": "incorrecta"})

        self.assertEqual(len(captured.records), 1)
        record = captured.records[0]
        self.assertEqual(record.levelname, "WARNING")
        self.assertIn("INTENTO_FALLIDO_LOGIN", record.getMessage())

    def test_successful_login_does_not_log_failed_attempt(self):
        response, output = self._login_capturing_stdout(VALID_EMAIL, VALID_PASSWORD)

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["token"])
        self.assertEqual(body["user"], {"name": "Admin QA", "role": "Lead QA"})
        self.assertNotIn("INTENTO_FALLIDO_LOGIN", output)
        self.assertIn("[INFO]", output)
        self.assertIn("LOGIN_EXITOSO", output)

    def test_protected_endpoint_without_token_logs_unauthorized_access(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            response = self.client.get("/api/v1/dashboard/metrics")

        self.assertEqual(response.status_code, 401)
        output = buffer.getvalue()
        self.assertIn("[WARNING]", output)
        self.assertIn("ACCESO_NO_AUTORIZADO", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
