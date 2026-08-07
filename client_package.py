"""Builds the printable Client Package PDF: a branded invoice/material
breakdown, project photos, and a contract page with a deposit/balance
split and a signature line the client signs by hand after printing."""
import os
from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
    Image as RLImage, HRFlowable, KeepTogether
)

PAGE_W, PAGE_H = letter
MARGIN = 50
HEADER_H = 72
CONTENT_W = PAGE_W - 2 * MARGIN

BRAND_DARK = colors.HexColor("#3d2314")
BRAND_ACCENT = colors.HexColor("#8B4513")
GREEN = colors.HexColor("#198754")
GREEN_DARK = colors.HexColor("#146c43")
TAN = colors.HexColor("#f3ece2")
ROW_ALT = colors.HexColor("#faf7f3")
BORDER = colors.HexColor("#e2d9cc")
TEXT_DARK = colors.HexColor("#212529")
MUTED = colors.HexColor("#6c757d")

LABELS = {
    "en": {
        "brand": "BYZEWO CABINET WORKS",
        "tagline": "Professional Cabinet Estimates & Installation",
        "title": "Client Package",
        "invoice": "INVOICE",
        "estimate": "ESTIMATE",
        "prepared_for": "Prepared for",
        "date": "Date",
        "item": "Item", "qty": "Qty", "unit_price": "Unit Price", "line_total": "Total",
        "materials": "Materials",
        "hardware": "Hardware & Accessories",
        "labor": "Labor",
        "total": "Total Due",
        "deposit_note": "50% deposit reserves your date · balance due at installation",
        "photos": "Project Photos",
        "contract": "Contract & Terms",
        "additional_rules": "Additional Rules for This Job",
        "payment_schedule": "Payment Schedule",
        "deposit_line": "Deposit (50%) — due to reserve your production/installation date",
        "balance_line": "Balance (50%) — due upon completion of installation",
        "client_signature": "Client Signature",
        "contractor_signature": "Contractor Signature",
        "print_name": "Print Name / Date",
        "footer": "byZewo Cabinet Works",
        "page": "Page",
        "of": "of",
    },
    "es": {
        "brand": "BYZEWO CABINET WORKS",
        "tagline": "Presupuestos e Instalación de Gabinetes Profesionales",
        "title": "Paquete del Cliente",
        "invoice": "FACTURA",
        "estimate": "PRESUPUESTO",
        "prepared_for": "Preparado para",
        "date": "Fecha",
        "item": "Artículo", "qty": "Cant.", "unit_price": "Precio Unit.", "line_total": "Total",
        "materials": "Materiales",
        "hardware": "Herrajes y Accesorios",
        "labor": "Mano de Obra",
        "total": "Total a Pagar",
        "deposit_note": "50% de depósito reserva su fecha · saldo al instalar",
        "photos": "Fotos del Proyecto",
        "contract": "Contrato y Términos",
        "additional_rules": "Reglas Adicionales para Este Trabajo",
        "payment_schedule": "Calendario de Pagos",
        "deposit_line": "Depósito (50%) — requerido para reservar su fecha de producción/instalación",
        "balance_line": "Saldo (50%) — debe pagarse al finalizar la instalación",
        "client_signature": "Firma del Cliente",
        "contractor_signature": "Firma del Contratista",
        "print_name": "Nombre en Letra de Molde / Fecha",
        "footer": "byZewo Cabinet Works",
        "page": "Página",
        "of": "de",
    },
}

STANDARD_RULES = {
    "en": """1. This estimate is valid for 30 days from the date above; prices may change after that period.
2. A 50% deposit of the total amount is required to reserve your production and installation date. Work will not begin until the deposit is received.
3. The remaining 50% balance is due in full upon completion of installation.
4. Any changes to the agreed scope of work (materials, dimensions, design) after signing may result in additional charges and a revised timeline.
5. The client is responsible for providing clear, accessible work areas. Delays caused by inaccessible areas may result in rescheduling and additional fees.
6. If the client cancels after the deposit is paid, the deposit may be forfeited to cover materials already ordered and time reserved, at the contractor's discretion.
7. Material prices are subject to change based on market conditions prior to deposit payment.
8. By signing below, both parties agree to the terms, pricing, and scope of work described in this package.""",
    "es": """1. Este presupuesto es válido por 30 días a partir de la fecha indicada; los precios pueden cambiar después de ese período.
2. Se requiere un depósito del 50% del monto total para reservar la fecha de producción e instalación. El trabajo no comenzará hasta recibir el depósito.
3. El saldo restante del 50% debe pagarse en su totalidad al finalizar la instalación.
4. Cualquier cambio en el alcance del trabajo acordado (materiales, dimensiones, diseño) después de la firma puede generar cargos adicionales y un nuevo cronograma.
5. El cliente es responsable de proporcionar áreas de trabajo despejadas y accesibles. Los retrasos causados por áreas inaccesibles pueden resultar en reprogramación y cargos adicionales.
6. Si el cliente cancela después de haber pagado el depósito, este podrá perderse para cubrir materiales ya ordenados y el tiempo reservado, a discreción del contratista.
7. Los precios de los materiales están sujetos a cambios según las condiciones del mercado antes del pago del depósito.
8. Al firmar a continuación, ambas partes aceptan los términos, precios y alcance del trabajo descritos en este paquete.""",
}

ITEM_TYPE_KEYS = {"material": "materials", "hardware": "hardware", "labor": "labor"}


def _styles(lang):
    return {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=22,
                                 textColor=BRAND_DARK, leading=26),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=11,
                                    textColor=MUTED, leading=14),
        "meta": ParagraphStyle("meta", fontName="Helvetica", fontSize=10,
                                textColor=TEXT_DARK, leading=15),
        "meta_label": ParagraphStyle("meta_label", fontName="Helvetica-Bold", fontSize=8,
                                      textColor=MUTED, leading=11),
        "section": ParagraphStyle("section", fontName="Helvetica-Bold", fontSize=13,
                                   textColor=BRAND_DARK, leading=16),
        "section_total": ParagraphStyle("section_total", fontName="Helvetica-Bold", fontSize=11,
                                         textColor=BRAND_ACCENT, alignment=TA_RIGHT),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=9.5,
                                textColor=TEXT_DARK, leading=12),
        "cell_desc": ParagraphStyle("cell_desc", fontName="Helvetica", fontSize=8,
                                     textColor=MUTED, leading=10),
        "cell_right": ParagraphStyle("cell_right", fontName="Helvetica", fontSize=9.5,
                                      textColor=TEXT_DARK, alignment=TA_RIGHT),
        "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=9,
                              textColor=colors.white, leading=11),
        "th_right": ParagraphStyle("th_right", fontName="Helvetica-Bold", fontSize=9,
                                    textColor=colors.white, alignment=TA_RIGHT),
        "rule": ParagraphStyle("rule", fontName="Helvetica", fontSize=10, textColor=TEXT_DARK,
                                leading=14, leftIndent=16, firstLineIndent=-16, spaceAfter=6),
        "caption": ParagraphStyle("caption", fontName="Helvetica", fontSize=8,
                                   textColor=MUTED, alignment=1, spaceBefore=4),
        "sig_label": ParagraphStyle("sig_label", fontName="Helvetica", fontSize=9,
                                     textColor=TEXT_DARK),
        "sig_sub": ParagraphStyle("sig_sub", fontName="Helvetica", fontSize=8,
                                   textColor=MUTED),
    }


class NumberedCanvas(canvas.Canvas):
    """Buffers pages so the footer can print 'Page X of Y' — the total page
    count isn't known until every flowable has been laid out."""
    def __init__(self, *args, **kwargs):
        canvas.Canvas.__init__(self, *args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_footer(total)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def _draw_footer(self, total):
        lang = getattr(self, "_pkg_lang", "en")
        L = LABELS[lang]
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.75)
        self.line(MARGIN, 40, PAGE_W - MARGIN, 40)
        self.setFont("Helvetica", 8)
        self.setFillColor(MUTED)
        self.drawString(MARGIN, 27, L["footer"])
        self.drawRightString(PAGE_W - MARGIN, 27,
                              f"{L['page']} {self._pageNumber} {L['of']} {total}")


def _make_canvas(lang):
    def _factory(*args, **kwargs):
        c = NumberedCanvas(*args, **kwargs)
        c._pkg_lang = lang
        return c
    return _factory


def _draw_header_band(canvas_obj, doc, lang):
    L = LABELS[lang]
    canvas_obj.saveState()
    canvas_obj.setFillColor(BRAND_DARK)
    canvas_obj.rect(0, PAGE_H - HEADER_H, PAGE_W, HEADER_H, fill=1, stroke=0)
    canvas_obj.setFillColor(BRAND_ACCENT)
    canvas_obj.rect(0, PAGE_H - HEADER_H - 4, PAGE_W, 4, fill=1, stroke=0)
    canvas_obj.setFillColor(colors.white)
    canvas_obj.setFont("Helvetica-Bold", 17)
    canvas_obj.drawString(MARGIN, PAGE_H - 34, L["brand"])
    canvas_obj.setFont("Helvetica", 9)
    canvas_obj.setFillColor(colors.HexColor("#d8c9b8"))
    canvas_obj.drawString(MARGIN, PAGE_H - 50, L["tagline"])
    canvas_obj.restoreState()


def _item_table(rows, styles, L, col_widths):
    header = [
        Paragraph(L["item"], styles["th"]),
        Paragraph(L["qty"], styles["th_right"]),
        Paragraph(L["unit_price"], styles["th_right"]),
        Paragraph(L["line_total"], styles["th_right"]),
    ]
    data = [header]
    for item in rows:
        name_html = f"<b>{item['name']}</b>"
        if item.get("description"):
            name_html += f"<br/><font size=8 color='#6c757d'>{item['description']}</font>"
        data.append([
            Paragraph(name_html, styles["cell"]),
            Paragraph(f"{item['quantity']} {item.get('unit') or ''}", styles["cell_right"]),
            Paragraph(f"${float(item['unit_price']):,.2f}", styles["cell_right"]),
            Paragraph(f"${float(item['total_price']):,.2f}", styles["cell_right"]),
        ])

    t = Table(data, colWidths=col_widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_DARK),
        ("TOPPADDING", (0, 0), (-1, 0), 7),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style.append(("BACKGROUND", (0, i), (-1, i), ROW_ALT))
    t.setStyle(TableStyle(style))
    return t


def _photo_cell(path, styles, cell_w):
    max_w, max_h = cell_w - 16, 150
    try:
        reader = ImageReader(path)
        iw, ih = reader.getSize()
    except Exception:
        return Paragraph(os.path.basename(path), styles["caption"])
    scale = min(max_w / iw, max_h / ih)
    img = RLImage(path, width=iw * scale, height=ih * scale)
    img.hAlign = "CENTER"
    return img


def build_client_package_pdf(job, estimate, items, totals, images, contract_terms,
                              extra_rules, language="en"):
    """Returns a BytesIO PDF combining a branded invoice breakdown, project
    photos, and a printable contract page with a deposit/balance summary
    and signature lines.
    """
    lang = language if language in LABELS else "en"
    L = LABELS[lang]
    styles = _styles(lang)

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=HEADER_H + 30, bottomMargin=55,
    )

    def _on_page(canvas_obj, doc_obj):
        _draw_header_band(canvas_obj, doc_obj, lang)

    client_name = job.get("client_name") or "Client"
    created_at = estimate.get("created_at")
    date_str = created_at.strftime("%B %d, %Y") if hasattr(created_at, "strftime") else (created_at or "")
    doc_type = L["invoice"] if estimate.get("estimate_type") == "invoice" else L["estimate"]
    total_amount = float(estimate.get("amount") or 0)
    deposit = total_amount / 2
    balance = total_amount - deposit

    story = []

    # ---- Title row: name + type badge ----
    badge = Table([[Paragraph(doc_type, ParagraphStyle(
        "badge", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, alignment=1))]],
        colWidths=[70], rowHeights=[18])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN if doc_type == L["invoice"] else BRAND_ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    title_row = Table(
        [[Paragraph(estimate.get("name") or L["title"], styles["title"]), badge]],
        colWidths=[CONTENT_W - 80, 80],
    )
    title_row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(title_row)
    story.append(Spacer(1, 4))
    story.append(Paragraph(L["title"], styles["subtitle"]))
    story.append(Spacer(1, 14))
    story.append(HRFlowable(width=CONTENT_W, color=BORDER, thickness=1))
    story.append(Spacer(1, 10))

    meta = Table([
        [Paragraph(L["prepared_for"].upper(), styles["meta_label"]),
         Paragraph(L["date"].upper(), styles["meta_label"])],
        [Paragraph(client_name, styles["meta"]),
         Paragraph(str(date_str), styles["meta"])],
    ], colWidths=[CONTENT_W / 2, CONTENT_W / 2])
    meta.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, 0), 2)]))
    story.append(meta)
    story.append(Spacer(1, 20))

    # ---- Item breakdown ----
    grouped = {"material": [], "hardware": [], "labor": []}
    for item in items:
        if item["item_type"] in grouped:
            grouped[item["item_type"]].append(item)

    col_widths = [CONTENT_W * 0.46, CONTENT_W * 0.16, CONTENT_W * 0.18, CONTENT_W * 0.20]
    for item_type in ("material", "hardware", "labor"):
        rows = grouped[item_type]
        if not rows:
            continue
        heading = Table(
            [[Paragraph(L[ITEM_TYPE_KEYS[item_type]], styles["section"]),
              Paragraph(f"${totals.get(item_type, 0):,.2f}", styles["section_total"])]],
            colWidths=[CONTENT_W - 100, 100],
        )
        heading.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))
        story.append(heading)
        story.append(Spacer(1, 6))
        story.append(_item_table(rows, styles, L, col_widths))
        story.append(Spacer(1, 16))

    # ---- Total box ----
    total_box = Table(
        [[Paragraph(L["total"], ParagraphStyle("tb", fontName="Helvetica-Bold", fontSize=12,
                                                 textColor=colors.white)),
          Paragraph(f"${total_amount:,.2f}", ParagraphStyle("ta", fontName="Helvetica-Bold",
                                                              fontSize=18, textColor=colors.white,
                                                              alignment=TA_RIGHT))]],
        colWidths=[CONTENT_W * 0.5, CONTENT_W * 0.5],
    )
    total_box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), GREEN_DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    story.append(total_box)
    story.append(Spacer(1, 6))
    story.append(Paragraph(L["deposit_note"],
                            ParagraphStyle("dn", fontName="Helvetica-Oblique", fontSize=8.5,
                                           textColor=MUTED, alignment=TA_RIGHT)))

    # ---- Photos ----
    valid_images = []
    for img in images:
        path = img if isinstance(img, str) else img.get("path")
        if path and os.path.exists(path):
            valid_images.append(path)

    if valid_images:
        from reportlab.platypus import PageBreak
        story.append(PageBreak())
        story.append(Paragraph(L["photos"], styles["section"]))
        story.append(Spacer(1, 4))
        story.append(HRFlowable(width=60, color=BRAND_ACCENT, thickness=2))
        story.append(Spacer(1, 14))

        cols = 2
        gap = 14
        cell_w = (CONTENT_W - gap * (cols - 1)) / cols
        grid_rows = []
        row = []
        for i, path in enumerate(valid_images):
            row.append(_photo_cell(path, styles, cell_w))
            if len(row) == cols:
                grid_rows.append(row)
                row = []
        if row:
            while len(row) < cols:
                row.append("")
            grid_rows.append(row)

        photo_grid = Table(grid_rows, colWidths=[cell_w] * cols)
        photo_grid.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ]))
        story.append(photo_grid)

    # ---- Contract page ----
    from reportlab.platypus import PageBreak
    story.append(PageBreak())
    story.append(Paragraph(L["contract"], styles["section"]))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width=60, color=BRAND_ACCENT, thickness=2))
    story.append(Spacer(1, 14))

    for line in (contract_terms or "").split("\n"):
        if line.strip():
            story.append(Paragraph(line.strip(), styles["rule"]))

    if extra_rules and extra_rules.strip():
        story.append(Spacer(1, 10))
        story.append(Paragraph(L["additional_rules"],
                                ParagraphStyle("ar", fontName="Helvetica-Bold", fontSize=11,
                                               textColor=BRAND_DARK)))
        story.append(Spacer(1, 6))
        for line in extra_rules.split("\n"):
            if line.strip():
                story.append(Paragraph(f"•&nbsp;&nbsp;{line.strip()}", styles["rule"]))

    story.append(Spacer(1, 16))
    story.append(Paragraph(L["payment_schedule"],
                            ParagraphStyle("ps", fontName="Helvetica-Bold", fontSize=11,
                                           textColor=BRAND_DARK)))
    story.append(Spacer(1, 8))
    pay_table = Table([
        [Paragraph(L["deposit_line"], styles["cell"]),
         Paragraph(f"${deposit:,.2f}", ParagraphStyle("pd", fontName="Helvetica-Bold",
                                                        fontSize=11, textColor=GREEN_DARK,
                                                        alignment=TA_RIGHT))],
        [Paragraph(L["balance_line"], styles["cell"]),
         Paragraph(f"${balance:,.2f}", ParagraphStyle("pb", fontName="Helvetica-Bold",
                                                        fontSize=11, textColor=BRAND_DARK,
                                                        alignment=TA_RIGHT))],
    ], colWidths=[CONTENT_W * 0.7, CONTENT_W * 0.3])
    pay_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), TAN),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(pay_table)
    story.append(Spacer(1, 46))

    sig_col_w = (CONTENT_W - 30) / 2
    sig_cells = []
    for label in (L["client_signature"], L["contractor_signature"]):
        block = [
            HRFlowable(width=sig_col_w, color=TEXT_DARK, thickness=0.75),
            Spacer(1, 4),
            Paragraph(label, styles["sig_label"]),
            Spacer(1, 30),
            HRFlowable(width=sig_col_w, color=TEXT_DARK, thickness=0.75),
            Spacer(1, 4),
            Paragraph(L["print_name"], styles["sig_sub"]),
        ]
        sig_cells.append(block)
    sig_table = Table([sig_cells], colWidths=[sig_col_w, sig_col_w])
    sig_table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 30),
        ("LEFTPADDING", (1, 0), (1, 0), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(KeepTogether(sig_table))

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page, canvasmaker=_make_canvas(lang))
    buffer.seek(0)
    return buffer
