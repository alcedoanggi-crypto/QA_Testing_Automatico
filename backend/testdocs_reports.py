"""Documentos de QA en PDF y Excel: Plan de pruebas, Casos de prueba, Matriz de trazabilidad (RTM) y
Reporte de defectos (Bug Report)."""
import io
import os
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from reports_engine import now_str

PRIMARY = colors.HexColor("#1E3A8A")
GRID = colors.HexColor("#CBD5E1")
SOFT = colors.HexColor("#F1F5F9")
STATUS_COLORS = {
    "Aprobado": "#15803D", "Validado": "#15803D", "Fallido": "#B91C1C", "Con fallas": "#B91C1C",
    "Bloqueado": "#B45309", "Pendiente": "#1D4ED8", "No ejecutado": "#64748B", "Sin cobertura": "#B91C1C",
    "Omitido": "#64748B", "Crítica": "#7F1D1D", "Alta": "#B91C1C", "Media": "#B45309", "Baja": "#475569",
}
IMPACT = {
    "Crítica": "Bloquea una función principal o provoca pérdida de datos; no hay alternativa de uso.",
    "Alta": "Afecta una función importante; existe una alternativa difícil o el error es muy visible.",
    "Media": "Afecta una función secundaria o hay una alternativa razonable.",
    "Baja": "Detalle visual o de usabilidad sin impacto en la operación.",
}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif")


# ----------------------------------------------------------------------------- utilidades PDF
class _Pdf:
    def __init__(self, title, landscape_mode=False):
        self.buffer = io.BytesIO()
        size = landscape(A4) if landscape_mode else A4
        self.doc = SimpleDocTemplate(self.buffer, pagesize=size, leftMargin=1.5 * cm, rightMargin=1.5 * cm,
                                     topMargin=1.5 * cm, bottomMargin=1.6 * cm, title=title, author="QA Center")
        self.width = size[0] - 3 * cm
        styles = getSampleStyleSheet()
        self.styles = styles
        self.h1, self.h2, self.h3 = styles["Title"], styles["Heading2"], styles["Heading3"]
        self.body = styles["BodyText"].clone("body", fontSize=9, leading=11.5)
        self.cell = styles["BodyText"].clone("cell", fontSize=7.5, leading=9)
        self.cell_bold = self.cell.clone("cell_bold", fontName="Helvetica-Bold")
        self.stat_style = self.cell.clone("stat", leading=17)
        self.muted = self.body.clone("muted", textColor=colors.HexColor("#64748B"), fontSize=8)
        self.title = title
        self.story = []

    def p(self, text, style=None):
        return Paragraph(escape(str(text or "-")).replace("\n", "<br/>"), style or self.cell)

    def heading(self, text, subtitle=None):
        self.story += [Paragraph(escape(text), self.h1),
                       Paragraph(escape(subtitle or f"Generado: {now_str()}"), self.muted), Spacer(1, 0.3 * cm)]

    def section(self, text):
        self.story += [Spacer(1, 0.25 * cm), Paragraph(escape(text), self.h2)]

    def fields(self, pairs, label_width=4.5 * cm):
        rows = [[Paragraph(f"<b>{escape(k)}</b>", self.cell), self.p(v)] for k, v in pairs]
        table = Table(rows, colWidths=[label_width, self.width - label_width])
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, GRID), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                   ("BACKGROUND", (0, 0), (0, -1), SOFT)]))
        self.story.append(table)

    def table(self, header, rows, widths, status_cols=()):
        data = [[Paragraph(f"<b>{escape(h)}</b>", self.cell.clone("hdr", textColor=colors.white)) for h in header]]
        data += [[cell if hasattr(cell, "wrap") else self.p(cell) for cell in row] for row in rows]
        style = [("BACKGROUND", (0, 0), (-1, 0), PRIMARY), ("GRID", (0, 0), (-1, -1), 0.4, GRID),
                 ("VALIGN", (0, 0), (-1, -1), "TOP")]
        for i in range(2, len(data), 2):
            style.append(("BACKGROUND", (0, i), (-1, i), SOFT))
        for col in status_cols:
            for i, row in enumerate(rows, start=1):
                color = STATUS_COLORS.get(str(row[col]))
                if color:
                    data[i][col] = Paragraph(f'<font color="{color}"><b>{escape(str(row[col]))}</b></font>', self.cell)
        table = Table(data, colWidths=[w * self.width for w in widths], repeatRows=1)
        table.setStyle(TableStyle(style))
        self.story.append(table)

    def stats(self, pairs):
        cells = [[Paragraph(f'<font size="15"><b>{escape(str(v))}</b></font><br/>'
                            f'<font size="7" color="#64748B">{escape(k)}</font>', self.stat_style) for k, v in pairs]]
        table = Table(cells, colWidths=[self.width / len(pairs)] * len(pairs))
        table.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.4, GRID), ("INNERGRID", (0, 0), (-1, -1), 0.4, GRID),
                                   ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        self.story.append(table)

    def image(self, path, max_width=None, max_height=11 * cm):
        try:
            from PIL import Image as PILImage
            with PILImage.open(path) as probe:
                probe.load()  # una imagen dañada no debe romper el documento
            img = Image(path)
        except Exception:
            self.story.append(self.p("(No se pudo incrustar la imagen: archivo dañado o formato no soportado)",
                                     self.muted))
            return
        width = min(max_width or self.width, self.width)
        ratio = img.imageHeight / float(img.imageWidth or 1)
        if width * ratio > max_height:
            width = max_height / ratio
        img.drawWidth, img.drawHeight = width, width * ratio
        self.story.append(img)

    def build(self):
        title = self.title

        def footer(canvas, document):
            canvas.saveState()
            canvas.setFont("Helvetica", 7.5)
            canvas.setFillColor(colors.HexColor("#64748B"))
            canvas.drawString(document.leftMargin, 0.8 * cm, f"QA Center · {title}")
            canvas.drawRightString(document.pagesize[0] - document.rightMargin, 0.8 * cm, f"Página {document.page}")
            canvas.restoreState()

        self.doc.build(self.story, onFirstPage=footer, onLaterPages=footer)
        self.buffer.seek(0)
        return self.buffer


# ----------------------------------------------------------------------------- utilidades Excel
class _Xlsx:
    def __init__(self):
        self.wb = Workbook()
        self._first = True
        thin = Side(style="thin", color="CBD5E1")
        self.border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def sheet(self, title, headers, rows, widths, wrap_cols=(), title_line=None):
        ws = self.wb.active if self._first else self.wb.create_sheet()
        self._first = False
        ws.title = title[:31]
        start = 1
        if title_line:
            ws.cell(row=1, column=1, value=title_line).font = Font(bold=True, size=13, color="1E3A8A")
            start = 3
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row=start, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1E3A8A")
            cell.border = self.border
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for r, values in enumerate(rows, start=start + 1):
            for col, value in enumerate(values, start=1):
                cell = ws.cell(row=r, column=col, value=value)
                cell.border = self.border
                cell.alignment = Alignment(vertical="top", wrap_text=col in wrap_cols)
                color = STATUS_COLORS.get(str(value)) if isinstance(value, str) else None
                if color:
                    cell.font = Font(bold=True, color=color.lstrip("#"))
        for col, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(col)].width = width
        ws.freeze_panes = ws.cell(row=start + 1, column=1)
        if rows:
            ws.auto_filter.ref = f"A{start}:{get_column_letter(len(headers))}{start + len(rows)}"
        return ws

    def key_values(self, title, pairs):
        ws = self.wb.active if self._first else self.wb.create_sheet()
        self._first = False
        ws.title = title[:31]
        for r, (key, value) in enumerate(pairs, start=1):
            ws.cell(row=r, column=1, value=key).font = Font(bold=True)
            cell = ws.cell(row=r, column=2, value=value)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.column_dimensions["A"].width = 28
        ws.column_dimensions["B"].width = 110
        return ws

    def build(self):
        buffer = io.BytesIO()
        self.wb.save(buffer)
        buffer.seek(0)
        return buffer


def _reqs(spec):
    return ", ".join(r["code"] for r in spec.get("requirements", [])) or "-"


CASE_HEADERS = ["ID", "Descripción", "Requisitos", "Módulo", "Tipo", "Prioridad", "Precondiciones",
                "Datos de entrada", "Pasos", "Resultado esperado", "Resultado obtenido", "Estado", "Ejecutado por",
                "Fecha ejecución", "Evidencias", "Defecto"]
CASE_WIDTHS = [10, 40, 14, 16, 13, 10, 35, 30, 50, 40, 40, 13, 18, 18, 35, 11]


def _case_row(s):
    return [s["code"], s["title"] + (f"\n{s['description']}" if s["description"] else ""), _reqs(s), s["module"],
            s["type"], s["priority"], s["preconditions"], s["input_data"], s["steps"], s["expected"], s["actual"],
            s["status"], s["executed_by"], s["executed_at"],
            "\n".join(filter(None, [s.get("evidence_notes", "")] + [e["filename"] for e in s.get("evidence", [])])),
            s.get("incident_code") or ""]


# ----------------------------------------------------------------------------- Plan de pruebas
PLAN_SECTIONS = [("1. Objetivo", "objective"), ("2. Alcance (incluido)", "scope_in"),
                 ("3. Fuera de alcance", "scope_out"), ("4. Funciones a evaluar", "features"),
                 ("5. Estrategia / enfoque de pruebas", "approach"),
                 ("6. Criterios de aceptación / éxito", "acceptance_criteria"),
                 ("7. Recursos necesarios", "resources"), ("8. Cronograma de trabajo", "schedule"),
                 ("9. Riesgos y contingencias", "risks")]


def plan_report(plan, specs, rtm, fmt):
    summary = plan["summary"]
    general = [("Código", plan["code"]), ("Nombre", plan["name"]), ("Versión", plan["version"]),
               ("Estado", plan["status"]), ("Responsable", plan["responsible"]), ("Ambiente", plan["environment"]),
               ("Fechas", f"{plan['start_date'] or '?'} a {plan['end_date'] or '?'}"),
               ("Última actualización", plan["updated_at"])]
    if fmt == "excel":
        x = _Xlsx()
        x.key_values("Plan", general + [(label, plan[key]) for label, key in PLAN_SECTIONS] + [
            ("Casos", summary["cases"]), ("Ejecutados", f"{summary['executed']} ({summary['execution_rate']} %)"),
            ("Aprobados", summary["by_status"]["Aprobado"]), ("Fallidos", summary["by_status"]["Fallido"]),
            ("Pass rate", f"{summary['pass_rate']} %"), ("Cobertura de requisitos", f"{summary['coverage']} %")])
        x.sheet("Casos de prueba", CASE_HEADERS, [_case_row(s) for s in specs], CASE_WIDTHS, wrap_cols=range(1, 17))
        _rtm_sheet(x, rtm)
        return x.build(), XLSX, f"plan_{plan['code']}.xlsx"

    pdf = _Pdf(f"Plan de pruebas {plan['code']}")
    pdf.heading(f"Plan de pruebas: {plan['name']}", f"{plan['code']} · versión {plan['version']} · {plan['status']}"
                f" · generado {now_str()}")
    pdf.fields(general)
    pdf.section("Estado de avance")
    pdf.stats([("Casos", summary["cases"]), ("Ejecutados", f"{summary['execution_rate']} %"),
               ("Aprobados", summary["by_status"]["Aprobado"]), ("Fallidos", summary["by_status"]["Fallido"]),
               ("Pass rate", f"{summary['pass_rate']} %"), ("Cobertura req.", f"{summary['coverage']} %")])
    for label, key in PLAN_SECTIONS:
        pdf.section(label)
        pdf.story.append(pdf.p(plan[key] or "No definido.", pdf.body))
    pdf.section("10. Casos de prueba del plan")
    if specs:
        pdf.table(["ID", "Caso", "Requisitos", "Tipo", "Prioridad", "Estado"],
                  [[s["code"], s["title"], _reqs(s), s["type"], s["priority"], s["status"]] for s in specs],
                  [0.1, 0.44, 0.14, 0.12, 0.1, 0.1], status_cols=(5,))
    else:
        pdf.story.append(pdf.p("Aún no hay casos de prueba asociados.", pdf.body))
    pdf.section("11. Trazabilidad de requisitos")
    _rtm_pdf_table(pdf, rtm)
    return pdf.build(), "application/pdf", f"plan_{plan['code']}.pdf"


# ----------------------------------------------------------------------------- Casos de prueba
def cases_report(specs, fmt, title="Casos de prueba", evidence_dir=None):
    if fmt == "excel":
        x = _Xlsx()
        x.sheet("Casos de prueba", CASE_HEADERS, [_case_row(s) for s in specs], CASE_WIDTHS, wrap_cols=range(1, 17),
                title_line=f"{title} · generado {now_str()}")
        return x.build(), XLSX, "casos_de_prueba.xlsx"

    pdf = _Pdf(title)
    pdf.heading(title)
    counts = {}
    for s in specs:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    pdf.stats([("Casos", len(specs))] + [(k, counts.get(k, 0)) for k in
                                          ("Aprobado", "Fallido", "Bloqueado", "No ejecutado")])
    pdf.section("Resumen")
    pdf.table(["ID", "Caso", "Requisitos", "Módulo", "Estado", "Defecto"],
              [[s["code"], s["title"], _reqs(s), s["module"] or "-", s["status"], s.get("incident_code") or "-"]
               for s in specs], [0.1, 0.45, 0.13, 0.14, 0.1, 0.08], status_cols=(4,))
    for s in specs:
        pdf.story.append(PageBreak())
        _case_detail_pdf(pdf, s, evidence_dir)
    return pdf.build(), "application/pdf", "casos_de_prueba.pdf"


def _case_detail_pdf(pdf, s, evidence_dir):
    pdf.story.append(Paragraph(escape(f"{s['code']} · {s['title']}"), pdf.h2))
    pdf.fields([
        ("ID", s["code"]), ("Descripción / propósito", s["description"] or s["title"]),
        ("Plan", f"{s.get('plan_code') or '-'} {s.get('plan_name') or ''}"), ("Requisitos", _reqs(s)),
        ("Módulo / tipo", f"{s['module'] or '-'} · {s['type']} · prioridad {s['priority']}"),
        ("Herramienta / ambiente", f"{s['tool']} · {s['environment']}" + (f" · {s['url']}" if s["url"] else "")),
        ("Precondiciones", s["preconditions"]), ("Datos de entrada", s["input_data"]),
        ("Pasos a seguir", s["steps"]), ("Resultado esperado", s["expected"]),
        ("Resultado obtenido", s["actual"]), ("Estado", s["status"]),
        ("Ejecutado por / fecha", f"{s['executed_by'] or '-'} · {s['executed_at'] or '-'}"),
        ("Defecto asociado", s.get("incident_code") or "-"),
        ("Evidencias / logs", s.get("evidence_notes") or "-"),
    ])
    evidence = s.get("evidence") or []
    if evidence:
        pdf.story.append(Spacer(1, 0.2 * cm))
        pdf.story.append(Paragraph("Evidencias adjuntas", pdf.h3))
        for ev in evidence:
            pdf.story.append(pdf.p(f"• {ev['filename']} ({round(ev['size'] / 1024, 1)} KB, {ev['created_at']})", pdf.body))
            path = os.path.join(evidence_dir or "", ev["stored_name"])
            if evidence_dir and ev["stored_name"].lower().endswith(IMAGE_EXT) and os.path.isfile(path):
                pdf.image(path, max_width=14 * cm, max_height=9 * cm)
                pdf.story.append(Spacer(1, 0.2 * cm))


def case_report(spec, fmt, evidence_dir=None):
    if fmt == "excel":
        x = _Xlsx()
        x.key_values(spec["code"], list(zip(CASE_HEADERS, _case_row(spec))))
        x.sheet("Ejecuciones", ["Estado", "Resultado obtenido", "Ejecutado por", "Fecha", "Defecto"],
                [[e["status"], e["actual"], e["executed_by"], e["executed_at"], e.get("incident_code") or ""]
                 for e in spec.get("executions", [])], [13, 70, 20, 20, 12], wrap_cols=(2,))
        return x.build(), XLSX, f"caso_{spec['code']}.xlsx"
    pdf = _Pdf(f"Caso de prueba {spec['code']}")
    pdf.heading(f"Caso de prueba {spec['code']}")
    _case_detail_pdf(pdf, spec, evidence_dir)
    if spec.get("executions"):
        pdf.section("Historial de ejecuciones")
        pdf.table(["Fecha", "Estado", "Resultado obtenido", "Por", "Defecto"],
                  [[e["executed_at"], e["status"], e["actual"] or "-", e["executed_by"], e.get("incident_code") or "-"]
                   for e in spec["executions"]], [0.18, 0.12, 0.45, 0.15, 0.1], status_cols=(1,))
    return pdf.build(), "application/pdf", f"caso_{spec['code']}.pdf"


# ----------------------------------------------------------------------------- Matriz de trazabilidad
def _rtm_cases_text(row):
    return "\n".join(f"{c['code']} ({c['status']})" for c in row["cases"]) or "—"


def _rtm_pdf_table(pdf, rtm):
    if not rtm["rows"]:
        pdf.story.append(pdf.p("No hay requisitos registrados.", pdf.body))
        return
    pdf.table(["Requisito", "Descripción", "Tipo", "Prioridad", "Casos de prueba", "Defectos", "Cobertura"],
              [[r["code"], r["title"], r["kind"], r["priority"], _rtm_cases_text(r), ", ".join(r["defects"]) or "-",
                r["coverage"]] for r in rtm["rows"]],
              [0.1, 0.3, 0.13, 0.09, 0.19, 0.09, 0.1], status_cols=(6,))


def _rtm_sheet(x, rtm):
    x.sheet("Trazabilidad", ["Requisito", "Descripción", "Tipo", "Módulo", "Prioridad", "Casos de prueba",
                             "Defectos", "Cobertura"],
            [[r["code"], r["title"], r["kind"], r["module"], r["priority"], _rtm_cases_text(r),
              ", ".join(r["defects"]), r["coverage"]] for r in rtm["rows"]],
            [12, 45, 18, 16, 10, 30, 14, 14], wrap_cols=(2, 6))


def rtm_report(rtm, fmt, plan=None):
    title = "Matriz de trazabilidad" + (f" · {plan['code']} {plan['name']}" if plan else "")
    totals = rtm["totals"]
    if fmt == "excel":
        x = _Xlsx()
        _rtm_sheet(x, rtm)
        # Matriz cruzada requisito × caso (X = cubierto).
        case_codes = sorted({c["code"] for r in rtm["rows"] for c in r["cases"]})
        x.sheet("Matriz cruzada", ["Requisito"] + case_codes,
                [[r["code"]] + [next((c["status"][:1] for c in r["cases"] if c["code"] == code), "")
                                for code in case_codes] for r in rtm["rows"]],
                [14] + [9] * len(case_codes))
        if rtm["orphan_cases"]:
            x.sheet("Casos sin requisito", ["ID", "Caso", "Estado"],
                    [[c["code"], c["title"], c["status"]] for c in rtm["orphan_cases"]], [10, 60, 14])
        return x.build(), XLSX, "matriz_trazabilidad.xlsx"
    pdf = _Pdf(title, landscape_mode=True)
    pdf.heading(title)
    by = totals["by_coverage"]
    pdf.stats([("Requisitos", totals["requirements"]), ("Con casos", totals["covered"]),
               ("Cobertura", f"{totals['coverage']} %"), ("Validados", by.get("Validado", 0)),
               ("Con fallas", by.get("Con fallas", 0)), ("Sin cobertura", by.get("Sin cobertura", 0))])
    pdf.section("Requisitos y casos de prueba")
    _rtm_pdf_table(pdf, rtm)
    if rtm["orphan_cases"]:
        pdf.section("Casos de prueba sin requisito asociado")
        pdf.table(["ID", "Caso", "Estado"], [[c["code"], c["title"], c["status"]] for c in rtm["orphan_cases"]],
                  [0.12, 0.73, 0.15], status_cols=(2,))
    return pdf.build(), "application/pdf", "matriz_trazabilidad.pdf"


# ----------------------------------------------------------------------------- Reporte de defectos
DEFECT_HEADERS = ["ID", "Título", "Severidad", "Impacto", "Prioridad", "Estado", "Asignado a", "Módulo", "Ambiente",
                  "URL", "Pasos para reproducir", "Resultado esperado", "Resultado obtenido", "Origen",
                  "Veces detectado", "Reportado por", "Fecha"]


def _defect_row(i):
    return [i["code"], i["title"], i["severity"], IMPACT.get(i["severity"], ""), i["priority"], i["status"],
            i.get("developer_name") or "Sin asignar", i["module"], i["environment"], i["url"], i["steps"],
            i["expected"], i["actual"], f"{i['source']} {i['source_ref']}".strip(), i["occurrences"],
            i["reported_by"], i["created_at"]]


def defects_report(incidents, fmt, title="Reporte de defectos"):
    if fmt == "excel":
        x = _Xlsx()
        x.sheet("Defectos", DEFECT_HEADERS, [_defect_row(i) for i in incidents],
                [10, 45, 11, 40, 10, 13, 20, 16, 10, 35, 50, 35, 50, 22, 9, 18, 18],
                wrap_cols=(2, 4, 11, 12, 13), title_line=f"{title} · generado {now_str()}")
        return x.build(), XLSX, "reporte_defectos.xlsx"
    pdf = _Pdf(title)
    pdf.heading(title)
    sev = {s: sum(1 for i in incidents if i["severity"] == s) for s in ("Crítica", "Alta", "Media", "Baja")}
    open_n = sum(1 for i in incidents if i["status"] in ("Nueva", "Asignada", "En progreso", "Reabierta"))
    pdf.stats([("Defectos", len(incidents)), ("Abiertos", open_n)] + list(sev.items()))
    pdf.section("Listado")
    pdf.table(["ID", "Título", "Severidad", "Estado", "Asignado a"],
              [[i["code"], i["title"], i["severity"], i["status"], i.get("developer_name") or "Sin asignar"]
               for i in incidents], [0.11, 0.5, 0.12, 0.12, 0.15], status_cols=(2,))
    for i in incidents:
        pdf.story.append(Spacer(1, 0.4 * cm))
        pdf.story.append(KeepTogether([Paragraph(escape(f"{i['code']} · {i['title']}"), pdf.h3)]))
        _defect_fields(pdf, i)
    return pdf.build(), "application/pdf", "reporte_defectos.pdf"


def _defect_fields(pdf, i):
    pdf.fields([
        ("Severidad / impacto", f"{i['severity']}: {IMPACT.get(i['severity'], '')}"),
        ("Prioridad / estado", f"{i['priority']} · {i['status']}"),
        ("Asignado a", i.get("developer_name") or "Sin asignar"),
        ("Módulo / ambiente", f"{i['module'] or '-'} · {i['environment']}"), ("URL", i["url"]),
        ("Descripción", i["description"]), ("Pasos para reproducir", i["steps"]),
        ("Resultado esperado", i["expected"]), ("Resultado obtenido", i["actual"]),
        ("Origen", f"{i['source']} {i['source_ref']}".strip()), ("Veces detectado", i["occurrences"]),
        ("Reportado por / fecha", f"{i['reported_by']} · {i['created_at']}"),
        ("Fecha límite", i["due_date"] or "-"),
    ])


def defect_report(incident, fmt):
    if fmt == "excel":
        x = _Xlsx()
        x.key_values(incident["code"], list(zip(DEFECT_HEADERS, _defect_row(incident))))
        x.sheet("Historial", ["Fecha", "Tipo", "Detalle", "Autor"],
                [[h["created_at"], h["kind"], h["detail"], h["author"]] for h in incident.get("history", [])],
                [19, 14, 80, 20], wrap_cols=(3,))
        return x.build(), XLSX, f"defecto_{incident['code']}.xlsx"
    pdf = _Pdf(f"Defecto {incident['code']}")
    pdf.heading(f"Reporte de defecto {incident['code']}", incident["title"])
    _defect_fields(pdf, incident)
    if incident.get("history"):
        pdf.section("Historial")
        pdf.table(["Fecha", "Tipo", "Detalle", "Autor"],
                  [[h["created_at"], h["kind"], h["detail"], h["author"]] for h in incident["history"]],
                  [0.18, 0.13, 0.52, 0.17])
    return pdf.build(), "application/pdf", f"defecto_{incident['code']}.pdf"
