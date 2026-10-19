"""Pruebas del motor de pruebas automáticas, el programador y el registro de ejecuciones.

Ejecutar (desde la raíz del proyecto):
    python -m pytest tests/test_system_runner.py -v
"""
import io
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout

# Base de datos temporal: las pruebas no deben escribir en backend/data/qa_reports.db
os.environ.setdefault("QA_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="qa_reports_test_"), "qa_reports.db"))
BACKEND_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import automation  # noqa: E402
from app import create_app  # noqa: E402
from reports_engine import repository  # noqa: E402

LOGIN_URL = "/api/v1/auth/login"
EXECUTE_URL = "/api/v1/test-runs/execute"
REGISTER_URL = "/api/v1/test-runs"
METRICS_URL = "/api/v1/dashboard/metrics"


class SystemRunnerTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        client = cls.app.test_client()
        with redirect_stdout(io.StringIO()):
            token = client.post(LOGIN_URL, json={"email": "admin@test.com",
                                                 "password": "SecurePassword123"}).get_json()["token"]
        cls.headers = {"Authorization": f"Bearer {token}"}

    def setUp(self):
        self.client = self.app.test_client()

    def quiet(self, func, *args, **kwargs):
        with redirect_stdout(io.StringIO()):
            return func(*args, **kwargs)

    # ------------------------------------------------------------------ motor
    def test_run_system_tests_all_cases_pass_and_are_registered(self):
        runs_before = len(repository.get_runs())
        result = self.quiet(automation.run_system_tests, self.app)

        expected_cases = sum(len(cases) for _, cases in automation.SUITES)
        self.assertEqual(result["total"], expected_cases)
        self.assertEqual(result["failed"], 0, f"Casos fallidos: {result}")
        self.assertEqual(len(result["runs"]), len(automation.SUITES))
        self.assertEqual(len(repository.get_runs()), runs_before + len(automation.SUITES))

        batch = repository.get_latest_batch()
        self.assertEqual(batch["batch_id"], result["batch_id"])
        self.assertEqual(len(batch["cases"]), expected_cases)
        self.assertEqual(batch["trigger"], "Programada")

    def test_failed_case_is_recorded_with_detail(self):
        def broken_case(_ctx):
            raise AssertionError("Fallo forzado para la prueba")

        original = automation.SUITES
        automation.SUITES = [("Suite rota", [("Caso que siempre falla", broken_case)])]
        try:
            output = io.StringIO()
            with redirect_stdout(output):
                result = automation.run_system_tests(self.app)
        finally:
            automation.SUITES = original

        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["runs"][0]["status"], "Failed")
        case = repository.get_latest_batch()["cases"][0]
        self.assertEqual(case["status"], "Failed")
        self.assertEqual(case["detail"], "Fallo forzado para la prueba")
        self.assertIn("CASO_FALLIDO", output.getvalue())
        self.assertIn("[WARNING]", output.getvalue())

    def test_runner_rejects_concurrent_batches(self):
        automation._run_lock.acquire()
        try:
            with self.assertRaises(automation.RunnerBusyError):
                automation.run_system_tests(self.app)
            response = self.client.post(EXECUTE_URL, headers=self.headers)
            self.assertEqual(response.status_code, 409)
        finally:
            automation._run_lock.release()

    def test_scheduler_runs_batch_automatically(self):
        batch_before = repository.get_latest_batch()
        scheduler = automation.AutoTestScheduler(self.app, interval_minutes=60, initial_delay_seconds=0.1)
        with redirect_stdout(io.StringIO()):
            scheduler.start()
            deadline = time.time() + 30
            while time.time() < deadline:
                batch = repository.get_latest_batch()
                if batch and batch != batch_before and batch["trigger"] == "Programada":
                    break
                time.sleep(0.2)
            scheduler.stop()

        batch = repository.get_latest_batch()
        self.assertIsNotNone(batch)
        self.assertNotEqual(batch, batch_before, "El programador no ejecutó ningún lote")
        self.assertEqual(batch["executed_by"], automation.SYSTEM_USER)
        status = scheduler.status()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["interval_minutes"], 60)

    # ------------------------------------------------------------------ endpoints
    def test_execute_endpoint_requires_token(self):
        response = self.quiet(self.client.post, EXECUTE_URL)
        self.assertEqual(response.status_code, 401)

    def test_execute_endpoint_runs_batch_as_current_user(self):
        response = self.quiet(self.client.post, EXECUTE_URL, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["failed"], 0)
        self.assertTrue(all(run["executed_by"] == "Admin QA" for run in body["runs"]))
        self.assertTrue(all(run["trigger"] == "Manual" for run in body["runs"]))

    def test_register_manual_run(self):
        payload = {"suite": "Regresión", "environment": "Staging", "total": 50, "failed": 4, "skipped": 6,
                   "avg_response_ms": 320, "duration_s": 42.5}
        response = self.quiet(self.client.post, REGISTER_URL, headers=self.headers, json=payload)
        self.assertEqual(response.status_code, 201)
        run = response.get_json()
        self.assertTrue(run["run_id"].startswith("RUN-"))
        self.assertEqual(run["passed"], 40)
        self.assertEqual(run["pass_rate"], 80.0)
        self.assertEqual(run["status"], "Failed")
        self.assertEqual(run["trigger"], "Registro manual")

        metrics = self.client.get(METRICS_URL, headers=self.headers).get_json()
        self.assertIn(run["run_id"], [r["run_id"] for r in metrics["recent_executions"]])

    def test_register_manual_run_validation(self):
        invalid_payloads = [
            ({"environment": "QA", "total": 5}, "suite"),
            ({"suite": "X", "environment": "Marte", "total": 5}, "Ambiente"),
            ({"suite": "X", "environment": "QA", "total": 0}, "al menos 1"),
            ({"suite": "X", "environment": "QA", "total": 5, "failed": 4, "skipped": 2}, "no puede superar"),
            ({"suite": "X", "environment": "QA", "total": "abc"}, "numérico"),
            ({"suite": "X", "environment": "QA", "total": 5, "failed": -1}, "mayor o igual a 0"),
        ]
        for payload, expected in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(REGISTER_URL, headers=self.headers, json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertIn(expected, response.get_json()["error"])

    def test_metrics_include_automation_status_and_last_batch(self):
        self.quiet(automation.run_system_tests, self.app)
        metrics = self.client.get(METRICS_URL, headers=self.headers).get_json()
        self.assertFalse(metrics["automation"]["enabled"])  # create_app no inicia el programador
        self.assertIsNotNone(metrics["last_batch"])
        self.assertGreater(len(metrics["last_batch"]["cases"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
