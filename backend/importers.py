"""Importación de resultados generados por herramientas externas.

* Postman / Newman: ``newman run coleccion.json -r json --reporter-json-export resultado.json``
* Selenium, pytest, Cypress, Playwright, JMeter…: reporte JUnit XML
  (``pytest --junitxml=resultado.xml``, ``cypress run --reporter junit``, ``npx playwright test --reporter=junit``).
"""
import json
import xml.etree.ElementTree as ET

MAX_FILE_BYTES = 10 * 1024 * 1024


def _case(name, status, response_ms=0.0, detail=""):
    return {"name": str(name)[:300] or "(sin nombre)", "status": status,
            "response_ms": round(float(response_ms or 0), 2), "detail": str(detail or "")[:2000]}


def parse_newman(data: dict) -> dict:
    run = data.get("run") or {}
    if "executions" not in run and "stats" not in run:
        raise ValueError("El JSON no parece un reporte de Newman (falta 'run.executions')")
    cases, response_times = [], []
    for execution in run.get("executions") or []:
        request_name = (execution.get("item") or {}).get("name", "Petición")
        response = execution.get("response") or {}
        if response.get("responseTime") is not None:
            response_times.append(response["responseTime"])
        code = response.get("code")
        assertions = execution.get("assertions") or []
        if execution.get("requestError"):
            error = execution["requestError"]
            cases.append(_case(request_name, "Failed", response.get("responseTime"),
                               f"Error de petición: {error.get('message', error) if isinstance(error, dict) else error}"))
        for assertion in assertions:
            error = assertion.get("error")
            status = "Skipped" if assertion.get("skipped") else ("Failed" if error else "Passed")
            detail = ""
            if error:
                detail = (error.get("message") or str(error)) if isinstance(error, dict) else str(error)
                if code:
                    detail += f" (HTTP {code})"
            cases.append(_case(f"{request_name} › {assertion.get('assertion', 'aserción')}", status,
                               response.get("responseTime"), detail))
        if not assertions and not execution.get("requestError"):
            ok = code is None or code < 400
            cases.append(_case(request_name, "Passed" if ok else "Failed", response.get("responseTime"),
                               "" if ok else f"HTTP {code}"))
    if not cases:
        stats = (run.get("stats") or {}).get("assertions") or {}
        total, failed = stats.get("total", 0), stats.get("failed", 0)
        cases = [_case(f"Aserción {i + 1}", "Failed" if i < failed else "Passed") for i in range(total)]
    timings = run.get("timings") or {}
    duration_ms = (timings.get("completed") or 0) - (timings.get("started") or 0)
    avg = timings.get("responseAverage") or (sum(response_times) / len(response_times) if response_times else 0)
    collection = (data.get("collection") or {}).get("info") or {}
    return {"tool": "Postman", "suite": collection.get("name") or "Colección Postman", "cases": cases,
            "avg_response_ms": avg, "duration_s": max(duration_ms, 0) / 1000}


def parse_junit(content: bytes) -> dict:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"XML inválido: {exc}") from None
    suites = [root] if root.tag == "testsuite" else root.findall(".//testsuite")
    if root.tag not in ("testsuite", "testsuites"):
        raise ValueError("El XML no es un reporte JUnit (se esperaba <testsuites> o <testsuite>)")
    cases, duration = [], 0.0
    for suite in suites:
        try:
            duration += float(suite.get("time") or 0)
        except ValueError:
            pass
        for testcase in suite.findall("testcase"):
            name = testcase.get("name", "")
            classname = testcase.get("classname", "")
            full_name = f"{classname.split('.')[-1]} › {name}" if classname else name
            try:
                ms = float(testcase.get("time") or 0) * 1000
            except ValueError:
                ms = 0
            failure = testcase.find("failure")
            if failure is None:
                failure = testcase.find("error")
            if failure is not None:
                text_lines = (failure.text or "").strip().splitlines()
                detail = failure.get("message") or (text_lines[-1] if text_lines else "")
                cases.append(_case(full_name, "Failed", ms, detail))
            elif testcase.find("skipped") is not None:
                cases.append(_case(full_name, "Skipped", ms, testcase.find("skipped").get("message", "")))
            else:
                cases.append(_case(full_name, "Passed", ms))
    if not cases:
        raise ValueError("El reporte JUnit no contiene casos de prueba")
    name = root.get("name") or (suites[0].get("name") if suites else "") or "Suite importada"
    times = [c["response_ms"] for c in cases]
    return {"tool": None, "suite": name, "cases": cases, "avg_response_ms": sum(times) / len(times),
            "duration_s": duration or sum(times) / 1000}


def parse_report(filename: str, content: bytes) -> dict:
    """Detecta el formato y devuelve ``{tool, suite, cases, avg_response_ms, duration_s}``."""
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("El archivo supera los 10 MB")
    text = content.lstrip()
    if text[:1] in (b"{", b"["):
        try:
            data = json.loads(content.decode("utf-8-sig"))
        except ValueError as exc:
            raise ValueError(f"JSON inválido: {exc}") from None
        if not isinstance(data, dict):
            raise ValueError("Formato JSON no soportado")
        if "info" in data and "item" in data and "run" not in data:
            raise ValueError("Ese archivo es la colección de Postman, no el resultado. Ejecútala con Newman: "
                             "newman run coleccion.json -r json --reporter-json-export resultado.json")
        return parse_newman(data)
    if text[:1] == b"<":
        return parse_junit(content)
    raise ValueError(f"Formato no reconocido para '{filename}'. Use un JSON de Newman o un XML JUnit.")
