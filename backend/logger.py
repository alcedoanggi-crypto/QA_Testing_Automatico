"""Configuración centralizada de logs formateados para consola.

Formato de salida:
    [WARNING] [2026-10-19 09:00:00] INTENTO_FALLIDO_LOGIN - Email: admin@test.com | IP: 127.0.0.1
"""
import logging
import sys

LOGGER_NAME = "qa_reports"
LOG_FORMAT = "[%(levelname)s] [%(asctime)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class ConsoleHandler(logging.StreamHandler):
    """StreamHandler que siempre escribe en el ``sys.stdout`` vigente.

    Resolver el stream en cada emisión (en lugar de fijarlo al crear el handler)
    permite que las herramientas que redirigen ``sys.stdout`` —``contextlib.redirect_stdout``,
    ``capsys`` de pytest, etc.— capturen los mensajes de log.
    """

    def __init__(self):
        super().__init__(sys.stdout)

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, _value):
        # El stream se resuelve dinámicamente; se ignora cualquier asignación.
        pass


def get_logger() -> logging.Logger:
    """Devuelve el logger de la aplicación, configurándolo una única vez."""
    logger = logging.getLogger(LOGGER_NAME)
    if not any(isinstance(h, ConsoleHandler) for h in logger.handlers):
        handler = ConsoleHandler()
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_failed_login(email: str, ip: str) -> None:
    get_logger().warning("INTENTO_FALLIDO_LOGIN - Email: %s | IP: %s", email, ip)


def log_successful_login(email: str, ip: str) -> None:
    get_logger().info("LOGIN_EXITOSO - Email: %s | IP: %s", email, ip)


def log_unauthorized_access(path: str, ip: str, reason: str) -> None:
    get_logger().warning("ACCESO_NO_AUTORIZADO - Ruta: %s | IP: %s | Motivo: %s", path, ip, reason)


def log_report_exported(report_format: str, email: str) -> None:
    get_logger().info("REPORTE_EXPORTADO - Formato: %s | Usuario: %s", report_format.upper(), email)


def log_test_batch_started(batch_id: str, trigger: str, executed_by: str) -> None:
    get_logger().info("PRUEBAS_AUTOMATICAS_INICIADAS - Lote: %s | Origen: %s | Por: %s", batch_id, trigger, executed_by)


def log_test_batch_finished(batch_id: str, total: int, failed: int) -> None:
    level = get_logger().warning if failed else get_logger().info
    level("PRUEBAS_AUTOMATICAS_FINALIZADAS - Lote: %s | Casos: %d | Exitosos: %d | Fallidos: %d",
          batch_id, total, total - failed, failed)


def log_test_case_failed(batch_id: str, suite: str, name: str, detail: str) -> None:
    get_logger().warning("CASO_FALLIDO - Lote: %s | Suite: %s | Caso: %s | Detalle: %s", batch_id, suite, name, detail)


def log_manual_run_registered(run_id: str, suite: str, email: str) -> None:
    get_logger().info("EJECUCION_REGISTRADA - ID: %s | Suite: %s | Usuario: %s", run_id, suite, email)


def log_scheduler_error(error: str) -> None:
    get_logger().error("ERROR_PROGRAMADOR_PRUEBAS - %s", error)
