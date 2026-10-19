"""Analizador de URL: abre la aplicación en Chrome sin interfaz y captura lo que aparece en la consola.

Detecta:
  * ``console.error`` / ``console.warn`` de la aplicación.
  * Excepciones de JavaScript no capturadas y promesas rechazadas sin ``catch``.
  * Recursos que no cargan (scripts, CSS, imágenes) y peticiones fetch/XHR con HTTP 4xx/5xx o fallo de red.
  * Otros mensajes del navegador (CSP, contenido mixto, etc.).

Si Chrome/Selenium no está disponible usa un modo HTTP básico que solo revisa el estado de la página y
de los recursos enlazados (no puede ver errores de JavaScript).
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit

ENGINE_BROWSER = "Chrome (Selenium)"
ENGINE_HTTP = "HTTP básico"
PAGE_TIMEOUT_S = 30
MAX_ISSUES_PER_PAGE = 200

# Se inyecta antes de que cargue cualquier script de la página.
CAPTURE_HOOK = r"""
(function () {
  if (window.__qaIssues) { return; }
  var issues = window.__qaIssues = [];
  function text(args) {
    return Array.prototype.map.call(args, function (a) {
      if (a instanceof Error) { return a.stack || (a.name + ": " + a.message); }
      if (typeof a === "object") { try { return JSON.stringify(a); } catch (e) { return String(a); } }
      return String(a);
    }).join(" ");
  }
  function push(level, source, message, location, resource) {
    if (issues.length < 500) {
      issues.push({level: level, source: source, message: String(message).slice(0, 4000),
                   location: location || "", resource_url: resource || ""});
    }
  }
  ["error", "warn"].forEach(function (method) {
    var original = console[method];
    console[method] = function () {
      push(method === "error" ? "error" : "warning", "console", text(arguments));
      return original.apply(this, arguments);
    };
  });
  window.addEventListener("error", function (e) {
    var t = e.target;
    if (t && t !== window && (t.src || t.href)) {
      push("error", "network", "No se pudo cargar el recurso <" + t.tagName.toLowerCase() + ">", "", t.src || t.href);
    } else {
      var loc = e.filename ? e.filename + ":" + e.lineno + ":" + e.colno : "";
      push("error", "javascript", (e.error && e.error.stack) || e.message, loc);
    }
  }, true);
  window.addEventListener("unhandledrejection", function (e) {
    var r = e.reason;
    push("error", "javascript", "Promesa rechazada sin manejar: " + ((r && (r.stack || r.message)) || String(r)));
  });
})();
"""

_driver_lock = threading.Lock()
_driver_path = None  # se resuelve una vez y se reutiliza


class BrowserUnavailable(RuntimeError):
    pass


def _build_driver():
    global _driver_path
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError as exc:  # pragma: no cover - depende de la instalación
        raise BrowserUnavailable("Selenium no está instalado") from exc

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--ignore-certificate-errors")
    options.set_capability("goog:loggingPrefs", {"browser": "ALL", "performance": "ALL"})
    binary = os.environ.get("QA_CHROME_BINARY")
    if binary:
        options.binary_location = binary

    errors = []
    candidates = [_driver_path] if _driver_path else [os.environ.get("QA_CHROMEDRIVER") or None, "wdm"]
    for candidate in candidates:
        try:
            if candidate == "wdm":
                from webdriver_manager.chrome import ChromeDriverManager
                candidate = ChromeDriverManager().install()
            service = Service(executable_path=candidate) if candidate else Service()
            driver = webdriver.Chrome(service=service, options=options)
            _driver_path = candidate
            return driver
        except Exception as exc:  # se prueba el siguiente método
            errors.append(f"{type(exc).__name__}: {str(exc).splitlines()[0] if str(exc) else ''}")
    raise BrowserUnavailable("No se pudo iniciar Chrome. " + " | ".join(errors))


def _network_issues(perf_logs, page_url):
    """Traduce el log de rendimiento de Chrome (eventos CDP) a errores de red."""
    requests, issues, main_status = {}, [], None
    for entry in perf_logs:
        try:
            msg = json.loads(entry["message"])["message"]
        except (KeyError, ValueError, TypeError):
            continue
        method, params = msg.get("method"), msg.get("params", {})
        if method == "Network.requestWillBeSent":
            requests[params.get("requestId")] = (params.get("request", {}).get("url", ""), params.get("type", ""))
        elif method == "Network.responseReceived":
            response = params.get("response", {})
            status, url = response.get("status", 0), response.get("url", "")
            if params.get("type") == "Document" and main_status is None:
                main_status = status
            if status >= 400 and not url.startswith("data:"):
                issues.append({
                    "level": "error" if status >= 500 or params.get("type") in ("Script", "Stylesheet", "Document",
                                                                                  "XHR", "Fetch") else "warning",
                    "source": "network",
                    "message": f"HTTP {status} {response.get('statusText', '')} en {params.get('type', 'recurso')}".strip(),
                    "resource_url": url, "page_url": page_url, "location": "",
                })
        elif method == "Network.loadingFailed":
            if params.get("canceled") or params.get("errorText") == "net::ERR_ABORTED":
                continue
            url, kind = requests.get(params.get("requestId"), ("", params.get("type", "")))
            if url.startswith("data:"):
                continue
            issues.append({"level": "error", "source": "network",
                           "message": f"Fallo de red ({params.get('errorText', 'desconocido')}) en {kind or 'recurso'}",
                           "resource_url": url, "page_url": page_url, "location": ""})
    return issues, main_status


def _browser_log_issues(logs, page_url):
    issues = []
    for entry in logs:
        message = entry.get("message", "")
        # Ya cubiertos por el hook (console/excepciones) o por el log de red.
        if entry.get("source") in ("console-api", "network") or "Failed to load resource" in message \
                or "Uncaught" in message:
            continue
        level = {"SEVERE": "error", "WARNING": "warning"}.get(entry.get("level"))
        if level:
            issues.append({"level": level, "source": "navegador", "message": message, "page_url": page_url,
                           "resource_url": "", "location": ""})
    return issues


def _same_site_links(driver, base_url, seen):
    origin = urlsplit(base_url).netloc
    try:
        hrefs = driver.execute_script("return Array.from(document.querySelectorAll('a[href]')).map(a => a.href);")
    except Exception:
        return []
    links = []
    for href in hrefs or []:
        url = urldefrag(href)[0]
        parts = urlsplit(url)
        if parts.scheme in ("http", "https") and parts.netloc == origin and url not in seen \
                and not any(url.lower().endswith(ext) for ext in (".pdf", ".zip", ".png", ".jpg", ".xlsx", ".csv")) \
                and "logout" not in url.lower():
            links.append(url)
            seen.add(url)
    return links


def scan_with_browser(url, max_pages=1, wait_seconds=2.0, screenshot_path=None) -> dict:
    with _driver_lock:  # una sola instancia de Chrome a la vez
        driver = _build_driver()
    try:
        driver.set_page_load_timeout(PAGE_TIMEOUT_S)
        driver.execute_cdp_cmd("Network.enable", {})
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": CAPTURE_HOOK})

        queue, seen = [url], {urldefrag(url)[0]}
        issues, result = [], {"engine": ENGINE_BROWSER, "pages": []}
        while queue and len(result["pages"]) < max_pages:
            page_url = queue.pop(0)
            started = time.perf_counter()
            page_issues = []
            try:
                driver.get(page_url)
            except Exception as exc:
                page_issues.append({"level": "error", "source": "navegador", "page_url": page_url,
                                    "message": f"La página no cargó: {str(exc).splitlines()[0]}",
                                    "resource_url": "", "location": ""})
            time.sleep(max(0.0, wait_seconds))  # errores asíncronos (fetch, timers) tras la carga

            try:
                hooked = driver.execute_script("return window.__qaIssues || [];") or []
            except Exception:
                hooked = []
            for item in hooked:
                if not (item.get("source") == "network" and item.get("resource_url")):
                    page_issues.append({**item, "page_url": page_url})
            perf = driver.get_log("performance")
            network, status = _network_issues(perf, page_url)
            page_issues += network
            page_issues += _browser_log_issues(driver.get_log("browser"), page_url)
            # Recursos que fallaron y no aparecen en el log de red (p. ej. bloqueados)
            known = {i["resource_url"] for i in network}
            page_issues += [{**i, "page_url": page_url} for i in hooked
                            if i.get("source") == "network" and i.get("resource_url") not in known]

            try:
                timing = driver.execute_script(
                    "var n = performance.getEntriesByType('navigation')[0]; return n ? n.duration : null;")
            except Exception:
                timing = None
            title = ""
            try:
                title = driver.title
            except Exception:
                pass
            if not result["pages"]:
                result.update({"http_status": status, "page_title": title,
                               "load_ms": round(timing if timing else (time.perf_counter() - started) * 1000, 1)})
                if screenshot_path:
                    try:
                        result["has_screenshot"] = driver.save_screenshot(screenshot_path)
                    except Exception:
                        result["has_screenshot"] = False
            result["pages"].append({"url": page_url, "http_status": status, "issues": len(page_issues)})
            issues += _dedupe(page_issues)[:MAX_ISSUES_PER_PAGE]
            if len(result["pages"]) < max_pages:
                queue += _same_site_links(driver, url, seen)
        result["pages_scanned"] = len(result["pages"])
        return {**result, "issues": issues}
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def _dedupe(issues):
    seen, unique = set(), []
    for issue in issues:
        key = (issue["level"], issue["source"], issue["message"], issue.get("resource_url", ""))
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique


# ----------------------------------------------------------------------------- modo HTTP básico
class _AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets, self.title, self._in_title = [], "", False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("src"):
            self.assets.append(("script", attrs["src"]))
        elif tag == "link" and "stylesheet" in (attrs.get("rel") or "") and attrs.get("href"):
            self.assets.append(("stylesheet", attrs["href"]))
        elif tag == "img" and attrs.get("src") and not attrs["src"].startswith("data:"):
            self.assets.append(("imagen", attrs["src"]))
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data


def _fetch(url, timeout=15):
    request = urllib.request.Request(url, headers={"User-Agent": "QA-Center-Scanner/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        return exc.code, b""


def scan_with_http(url, reason="") -> dict:
    issues, started = [], time.perf_counter()
    note = "Sin navegador: solo se revisaron respuestas HTTP; no se capturan errores de JavaScript."
    if reason:
        note += f" Motivo: {reason}"
    try:
        status, body = _fetch(url)
    except Exception as exc:
        return {"engine": ENGINE_HTTP, "status": "Error", "http_status": None, "pages_scanned": 0,
                "message": f"No se pudo conectar con {url}: {exc}. ¿La aplicación está corriendo?",
                "issues": [{"level": "error", "source": "network", "message": f"No hay conexión: {exc}",
                            "page_url": url, "resource_url": url, "location": ""}]}
    load_ms = round((time.perf_counter() - started) * 1000, 1)
    if status >= 400:
        issues.append({"level": "error", "source": "network", "message": f"La página respondió HTTP {status}",
                       "page_url": url, "resource_url": url, "location": ""})
    parser = _AssetParser()
    try:
        parser.feed(body.decode("utf-8", errors="replace"))
    except Exception:
        pass
    for kind, src in parser.assets[:60]:
        asset_url = urljoin(url, src)
        try:
            asset_status, _ = _fetch(asset_url, timeout=10)
        except Exception as exc:
            issues.append({"level": "error", "source": "network", "message": f"Fallo de red en {kind}: {exc}",
                           "page_url": url, "resource_url": asset_url, "location": ""})
            continue
        if asset_status >= 400:
            issues.append({"level": "error", "source": "network", "message": f"HTTP {asset_status} en {kind}",
                           "page_url": url, "resource_url": asset_url, "location": ""})
    return {"engine": ENGINE_HTTP, "http_status": status, "load_ms": load_ms, "page_title": parser.title.strip(),
            "pages_scanned": 1, "message": note, "issues": issues}


def scan_url(url, max_pages=1, wait_seconds=2.0, screenshot_path=None, allow_fallback=True) -> dict:
    """Analiza ``url`` y devuelve ``{engine, http_status, load_ms, page_title, pages_scanned, message, issues}``."""
    try:
        result = scan_with_browser(url, max_pages, wait_seconds, screenshot_path)
    except BrowserUnavailable as exc:
        if not allow_fallback:
            raise
        return scan_with_http(url, reason=str(exc))
    if result.get("http_status") is None and result["issues"] and all(
            "ERR_CONNECTION_REFUSED" in i["message"] or "La página no cargó" in i["message"]
            for i in result["issues"][:1]):
        result["status"] = "Error"
        result["message"] = f"No se pudo abrir {url}. ¿La aplicación está corriendo?"
    pages = result.get("pages", [])
    if len(pages) > 1:
        result["message"] = (result.get("message", "") + " Páginas revisadas: "
                             + ", ".join(urlsplit(p["url"]).path or "/" for p in pages)).strip()
    return result
