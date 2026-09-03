"""Shared branding primitives for reportlab-based PDFs: palette, page
geometry, header band (with optional logo), fonts/styles, and reusable
flowable builders (item table, total box, doc-type badge, meta block)."""
import os

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import Table, TableStyle, Paragraph

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

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "img", "logo.png")

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
        "doc_number": "No.",
        "contact": "Contact",
        "phone": "Phone",
        "email": "Email",
        "address": "Address",
        "receipt_title": "Deposit Receipt",
        "received_from": "Received From",
        "receipt_for": "For",
        "amount_received": "Amount Received",
        "balance_remaining": "Balance Remaining",
        "payment_method": "Payment Method / Notes",
        "received_by": "Received By (Contractor)",
        "date_received": "Date Received",
        "receipt_note": "This receipt confirms the deposit payment noted above. Keep for your records.",
        "receipt_fillable_note": "To be completed by the contractor at the time the deposit is collected.",
        "installation_date": "Installation Date",
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
        "doc_number": "No.",
        "contact": "Contacto",
        "phone": "Teléfono",
        "email": "Correo Electrónico",
        "address": "Dirección",
        "receipt_title": "Recibo de Depósito",
        "received_from": "Recibido de",
        "receipt_for": "Por",
        "amount_received": "Monto Recibido",
        "balance_remaining": "Saldo Restante",
        "payment_method": "Método de Pago / Notas",
        "received_by": "Recibido Por (Contratista)",
        "date_received": "Fecha de Recepción",
        "receipt_note": "Este recibo confirma el pago del depósito indicado arriba. Consérvelo para sus registros.",
        "receipt_fillable_note": "A ser completado por el contratista al momento de recibir el depósito.",
        "installation_date": "Fecha de Instalación",
    },
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
        "meta_contact": ParagraphStyle("meta_contact", fontName="Helvetica", fontSize=8.5,
                                        textColor=MUTED, leading=12),
        "meta_install": ParagraphStyle("meta_install", fontName="Helvetica-Bold", fontSize=10,
                                        textColor=BRAND_ACCENT, leading=15),
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


class NumberedCanvas:
    """Mixin factory built in _make_canvas; see canvas subclass below."""


def _build_numbered_canvas_class():
    from reportlab.pdfgen import canvas as _canvas_mod

    class _NumberedCanvas(_canvas_mod.Canvas):
        """Buffers pages so the footer can print 'Page X of Y' — the total page
        count isn't known until every flowable has been laid out."""
        def __init__(self, *args, **kwargs):
            _canvas_mod.Canvas.__init__(self, *args, **kwargs)
            self._saved_page_states = []

        def showPage(self):
            self._saved_page_states.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved_page_states)
            for state in self._saved_page_states:
                self.__dict__.update(state)
                self._draw_footer(total)
                _canvas_mod.Canvas.showPage(self)
            _canvas_mod.Canvas.save(self)

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

    return _NumberedCanvas


_NumberedCanvasClass = _build_numbered_canvas_class()


def _make_canvas(lang):
    def _factory(*args, **kwargs):
        c = _NumberedCanvasClass(*args, **kwargs)
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

    text_x = MARGIN
    if os.path.exists(LOGO_PATH):
        try:
            reader = ImageReader(LOGO_PATH)
            iw, ih = reader.getSize()
            logo_h = HEADER_H - 26
            logo_w = logo_h * (iw / ih)
            canvas_obj.drawImage(LOGO_PATH, MARGIN, PAGE_H - HEADER_H + 13,
                                  width=logo_w, height=logo_h,
                                  preserveAspectRatio=True, mask='auto')
            text_x = MARGIN + logo_w + 12
        except Exception:
            text_x = MARGIN

    canvas_obj.setFillColor(colors.white)
    canvas_obj.setFont("Helvetica-Bold", 17)
    canvas_obj.drawString(text_x, PAGE_H - 34, L["brand"])
    canvas_obj.setFont("Helvetica", 9)
    canvas_obj.setFillColor(colors.HexColor("#d8c9b8"))
    canvas_obj.drawString(text_x, PAGE_H - 50, L["tagline"])
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


def build_doc_type_badge(label, color, width=70):
    badge = Table([[Paragraph(label, ParagraphStyle(
        "badge", fontName="Helvetica-Bold", fontSize=9, textColor=colors.white, alignment=1))]],
        colWidths=[width], rowHeights=[18])
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return badge


def build_total_box(label, amount, content_w, bg=GREEN_DARK):
    box = Table(
        [[Paragraph(label, ParagraphStyle("tb", fontName="Helvetica-Bold", fontSize=12,
                                           textColor=colors.white)),
          Paragraph(f"${amount:,.2f}", ParagraphStyle("ta", fontName="Helvetica-Bold",
                                                        fontSize=18, textColor=colors.white,
                                                        alignment=TA_RIGHT))]],
        colWidths=[content_w * 0.5, content_w * 0.5],
    )
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
    ]))
    return box


def build_meta_block(L, styles, client_name, date_str, doc_number, contact_lines, content_w,
                      installation_date_str=None):
    """Meta table: prepared-for/date labels + values, an optional doc number
    under the date, an optional contact line under the name, and an optional
    third "Installation Date" column highlighted in the accent color."""
    name_para = Paragraph(client_name, styles["meta"])
    if contact_lines:
        name_para = [name_para, Paragraph(" · ".join(contact_lines), styles["meta_contact"])]

    date_val = date_str
    if doc_number:
        date_val = [Paragraph(str(date_str), styles["meta"]),
                    Paragraph(f"{L['doc_number']} {doc_number}", styles["meta_contact"])]
    else:
        date_val = Paragraph(str(date_str), styles["meta"])

    if installation_date_str:
        install_val = Paragraph(str(installation_date_str), styles["meta_install"])
        meta = Table([
            [Paragraph(L["prepared_for"].upper(), styles["meta_label"]),
             Paragraph(L["date"].upper(), styles["meta_label"]),
             Paragraph(L["installation_date"].upper(), styles["meta_label"])],
            [name_para, date_val, install_val],
        ], colWidths=[content_w * 0.4, content_w * 0.3, content_w * 0.3])
    else:
        meta = Table([
            [Paragraph(L["prepared_for"].upper(), styles["meta_label"]),
             Paragraph(L["date"].upper(), styles["meta_label"])],
            [name_para, date_val],
        ], colWidths=[content_w / 2, content_w / 2])

    meta.setStyle(TableStyle([
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return meta
