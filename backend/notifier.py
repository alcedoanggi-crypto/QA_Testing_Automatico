"""Envío de novedades a los programadores: correo (SMTP) y webhook (Slack, Microsoft Teams, Discord o genérico)."""
import json
import smtplib
import ssl
import urllib.error
import urllib.request
from email.message import EmailMessage

TIMEOUT_S = 15


class NotificationError(RuntimeError):
    pass


def incident_link(incident, settings) -> str:
    base = (settings.get("public_base_url") or "").rstrip("/")
    return f"{base}/dashboard#novedades/{incident['id']}" if base else ""


def build_subject(incident) -> str:
    return f"[{incident['code']}] [{incident['severity']}] {incident['title']}"


def build_message(incident, settings, extra_note="") -> str:
    """Texto plano con todo lo que el programador necesita para reproducir y corregir."""
    lines = [
        f"Novedad {incident['code']}: {incident['title']}",
        "",
        f"Severidad: {incident['severity']}    Prioridad: {incident['priority']}    Estado: {incident['status']}",
        f"Ambiente: {incident['environment']}" + (f"    Módulo: {incident['module']}" if incident.get("module") else ""),
    ]
    if incident.get("url"):
        lines.append(f"URL: {incident['url']}")
    if incident.get("developer_name"):
        lines.append(f"Asignado a: {incident['developer_name']}")
    if incident.get("due_date"):
        lines.append(f"Fecha límite: {incident['due_date']}")
    lines.append(f"Reportado por: {incident['reported_by']} el {incident['created_at']}"
                 + (f" (origen: {incident['source']} {incident.get('source_ref') or ''})".rstrip() if incident.get("source") else ""))
    if incident.get("occurrences", 1) > 1:
        lines.append(f"Veces detectada: {incident['occurrences']}")
    for label, key in (("Descripción", "description"), ("Pasos para reproducir", "steps"),
                       ("Resultado esperado", "expected"), ("Resultado actual / error", "actual")):
        if incident.get(key):
            lines += ["", f"{label}:", incident[key]]
    if extra_note:
        lines += ["", "Nota de QA:", extra_note]
    link = incident_link(incident, settings)
    if link:
        lines += ["", f"Ver en QA Center: {link}"]
    return "\n".join(lines)


def send_email(settings, to_address, subject, body, attachments=None) -> None:
    """``to_address`` admite varios correos separados por coma; ``attachments`` = [(nombre, bytes, mimetype)]."""
    host = settings.get("smtp_host")
    if not host:
        raise NotificationError("El servidor de correo (SMTP) no está configurado")
    if not to_address:
        raise NotificationError("El programador no tiene correo")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.get("smtp_from") or settings.get("smtp_user") or "qa-center@localhost"
    message["To"] = to_address
    message.set_content(body)
    for filename, data, mimetype in attachments or []:
        maintype, _, subtype = mimetype.partition("/")
        message.add_attachment(data, maintype=maintype, subtype=subtype.split(";")[0], filename=filename)
    port = int(settings.get("smtp_port") or 587)
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT_S, context=ssl.create_default_context())
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT_S)
            if settings.get("smtp_tls", "1") == "1":
                server.starttls(context=ssl.create_default_context())
        with server:
            if settings.get("smtp_user"):
                server.login(settings["smtp_user"], settings.get("smtp_password", ""))
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise NotificationError(f"No se pudo enviar el correo: {exc}") from exc


def send_webhook(settings, subject, body) -> None:
    url = settings.get("webhook_url")
    if not url:
        raise NotificationError("No hay webhook configurado")
    text = f"*{subject}*\n{body}"
    # "text" lo entienden Slack y Teams; "content" lo usa Discord (máx. 2000 caracteres).
    payload = json.dumps({"text": text, "content": text[:1990]}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST",
                                     headers={"Content-Type": "application/json", "User-Agent": "QA-Center/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
            if response.status >= 300:
                raise NotificationError(f"El webhook respondió HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        raise NotificationError(f"El webhook respondió HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise NotificationError(f"No se pudo contactar el webhook: {exc}") from exc


def notify_incident(incident, settings, channels, extra_note="") -> dict:
    """Envía la novedad por los canales pedidos. Devuelve ``{canal: "ok" | mensaje de error}``."""
    subject = build_subject(incident)
    body = build_message(incident, settings, extra_note)
    results = {}
    for channel in channels:
        try:
            if channel == "email":
                send_email(settings, incident.get("developer_email"), subject, body)
            elif channel == "webhook":
                send_webhook(settings, subject, body)
            else:
                continue
            results[channel] = "ok"
        except NotificationError as exc:
            results[channel] = str(exc)
    return results


def available_channels(settings) -> list:
    channels = []
    if settings.get("smtp_host"):
        channels.append("email")
    if settings.get("webhook_url"):
        channels.append("webhook")
    return channels
