"""Builds the printable Client Package PDF: invoice/material breakdown,
job photos, and a contract page with a deposit/balance split and a
signature line the client signs by hand after printing."""
import os
from io import BytesIO

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader, simpleSplit

PAGE_W, PAGE_H = letter
MARGIN = 50

LABELS = {
    "en": {
        "title": "Client Package",
        "prepared_for": "Prepared for",
        "date": "Date",
        "materials": "Materials",
        "hardware": "Hardware & Accessories",
        "labor": "Labor",
        "total": "Total",
        "photos": "Project Photos",
        "contract": "Contract & Terms",
        "additional_rules": "Additional Rules for This Job",
        "payment_schedule": "Payment Schedule",
        "deposit_line": "Deposit (50%) due to reserve production/installation date:",
        "balance_line": "Balance (50%) due upon completion of installation:",
        "client_signature": "Client Signature",
        "contractor_signature": "Contractor Signature",
        "print_name": "Print Name",
        "signed_date": "Date",
        "page": "Page",
    },
    "es": {
        "title": "Paquete del Cliente",
        "prepared_for": "Preparado para",
        "date": "Fecha",
        "materials": "Materiales",
        "hardware": "Herrajes y Accesorios",
        "labor": "Mano de Obra",
        "total": "Total",
        "photos": "Fotos del Proyecto",
        "contract": "Contrato y Términos",
        "additional_rules": "Reglas Adicionales para Este Trabajo",
        "payment_schedule": "Calendario de Pagos",
        "deposit_line": "Depósito (50%) requerido para reservar la fecha de producción/instalación:",
        "balance_line": "Saldo (50%) que debe pagarse al finalizar la instalación:",
        "client_signature": "Firma del Cliente",
        "contractor_signature": "Firma del Contratista",
        "print_name": "Nombre en Letra de Molde",
        "signed_date": "Fecha",
        "page": "Página",
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

ITEM_TYPE_LABELS = {
    "en": {"material": "Materials", "hardware": "Hardware & Accessories", "labor": "Labor"},
    "es": {"material": "Materiales", "hardware": "Herrajes y Accesorios", "labor": "Mano de Obra"},
}


def _footer(p, page_num, lang):
    p.setFont("Helvetica", 8)
    p.setFillGray(0.5)
    p.drawRightString(PAGE_W - MARGIN, 25, f"{LABELS[lang]['page']} {page_num}")
    p.setFillGray(0)


def height_cursor_start(p, page_num, lang):
    _footer(p, page_num, lang)
    return PAGE_H - MARGIN


def _wrapped_lines(p, text, font, size, max_width):
    p.setFont(font, size)
    lines = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        lines.extend(simpleSplit(paragraph, font, size, max_width))
    return lines


def _draw_paragraph(p, text, x, y, max_width, font="Helvetica", size=10, leading=14,
                     page_num=1, lang="en"):
    """Draws wrapped text starting at (x, y), flowing to new pages as needed.
    Returns (new_y, new_page_num)."""
    for line in _wrapped_lines(p, text, font, size, max_width):
        if y < 70:
            _footer(p, page_num, lang)
            p.showPage()
            page_num += 1
            y = PAGE_H - MARGIN
            p.setFont(font, size)
        p.drawString(x, y, line)
        y -= leading
    return y, page_num


def build_client_package_pdf(job, estimate, items, totals, images, contract_terms,
                              extra_rules, language="en"):
    """Returns a BytesIO PDF combining the invoice breakdown, project photos,
    and a printable contract page with a deposit/balance summary and
    signature lines.
    """
    lang = language if language in LABELS else "en"
    L = LABELS[lang]

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    page_num = 1
    y = height_cursor_start(p, page_num, lang)

    client_name = job.get("client_name") or "Client"
    created_at = estimate.get("created_at")
    date_str = created_at.strftime("%B %d, %Y") if hasattr(created_at, "strftime") else (created_at or "")

    # ---- Cover / invoice header ----
    p.setFont("Helvetica-Bold", 20)
    p.drawString(MARGIN, y, L["title"])
    y -= 22
    p.setFont("Helvetica", 11)
    p.drawString(MARGIN, y, f"{estimate.get('name') or 'Cabinet Project'}")
    y -= 30

    p.setFont("Helvetica", 11)
    p.drawString(MARGIN, y, f"{L['prepared_for']}: {client_name}")
    y -= 16
    p.drawString(MARGIN, y, f"{L['date']}: {date_str}")
    y -= 30

    # ---- Item breakdown ----
    type_labels = ITEM_TYPE_LABELS[lang]
    grouped = {"material": [], "hardware": [], "labor": []}
    for item in items:
        if item["item_type"] in grouped:
            grouped[item["item_type"]].append(item)

    for item_type in ("material", "hardware", "labor"):
        rows = grouped[item_type]
        if not rows:
            continue
        if y < 120:
            _footer(p, page_num, lang)
            p.showPage()
            page_num += 1
            y = PAGE_H - MARGIN
        p.setFont("Helvetica-Bold", 13)
        p.drawString(MARGIN, y, f"{type_labels[item_type]} — ${totals.get(item_type, 0):,.2f}")
        y -= 18
        p.setFont("Helvetica", 10)
        for item in rows:
            if y < 80:
                _footer(p, page_num, lang)
                p.showPage()
                page_num += 1
                y = PAGE_H - MARGIN
                p.setFont("Helvetica", 10)
            line = f"{item['name']} — {item['quantity']} {item['unit']} x ${float(item['unit_price']):,.2f} = ${float(item['total_price']):,.2f}"
            p.drawString(MARGIN + 10, y, line)
            y -= 15
        y -= 10

    y -= 10
    if y < 80:
        _footer(p, page_num, lang)
        p.showPage()
        page_num += 1
        y = PAGE_H - MARGIN
    p.setFont("Helvetica-Bold", 14)
    total_amount = float(estimate.get("amount") or 0)
    p.drawString(MARGIN, y, f"{L['total']}: ${total_amount:,.2f}")
    y -= 30

    # ---- Photos ----
    if images:
        _footer(p, page_num, lang)
        p.showPage()
        page_num += 1
        y = height_cursor_start(p, page_num, lang)
        p.setFont("Helvetica-Bold", 16)
        p.drawString(MARGIN, y, L["photos"])
        y -= 25

        cols, rows_per_page = 2, 3
        cell_w = (PAGE_W - 2 * MARGIN - 20) / cols
        cell_h = 150
        col, row = 0, 0
        for img in images:
            path = img if isinstance(img, str) else img.get("path")
            if not path or not os.path.exists(path):
                continue
            try:
                reader = ImageReader(path)
                iw, ih = reader.getSize()
            except Exception:
                continue
            scale = min(cell_w / iw, cell_h / ih)
            dw, dh = iw * scale, ih * scale
            x = MARGIN + col * (cell_w + 20)
            cell_top = y - row * (cell_h + 15)
            draw_y = cell_top - dh
            p.drawImage(reader, x, draw_y, width=dw, height=dh, preserveAspectRatio=True, mask='auto')

            col += 1
            if col >= cols:
                col = 0
                row += 1
            if row >= rows_per_page:
                row, col = 0, 0
                _footer(p, page_num, lang)
                p.showPage()
                page_num += 1
                y = height_cursor_start(p, page_num, lang)

    # ---- Contract page ----
    _footer(p, page_num, lang)
    p.showPage()
    page_num += 1
    y = height_cursor_start(p, page_num, lang)

    p.setFont("Helvetica-Bold", 16)
    p.drawString(MARGIN, y, L["contract"])
    y -= 24

    max_width = PAGE_W - 2 * MARGIN
    y, page_num = _draw_paragraph(p, contract_terms or "", MARGIN, y, max_width,
                                   size=10, leading=14, page_num=page_num, lang=lang)

    if extra_rules and extra_rules.strip():
        y -= 12
        if y < 100:
            _footer(p, page_num, lang)
            p.showPage()
            page_num += 1
            y = height_cursor_start(p, page_num, lang)
        p.setFont("Helvetica-Bold", 12)
        p.drawString(MARGIN, y, L["additional_rules"])
        y -= 18
        y, page_num = _draw_paragraph(p, extra_rules, MARGIN, y, max_width,
                                       size=10, leading=14, page_num=page_num, lang=lang)

    # ---- Payment schedule ----
    y -= 15
    if y < 130:
        _footer(p, page_num, lang)
        p.showPage()
        page_num += 1
        y = height_cursor_start(p, page_num, lang)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(MARGIN, y, L["payment_schedule"])
    y -= 18
    deposit = total_amount / 2
    balance = total_amount - deposit
    p.setFont("Helvetica", 10)
    p.drawString(MARGIN, y, L["deposit_line"])
    p.drawRightString(PAGE_W - MARGIN, y, f"${deposit:,.2f}")
    y -= 16
    p.drawString(MARGIN, y, L["balance_line"])
    p.drawRightString(PAGE_W - MARGIN, y, f"${balance:,.2f}")
    y -= 40

    # ---- Signature lines ----
    if y < 110:
        _footer(p, page_num, lang)
        p.showPage()
        page_num += 1
        y = height_cursor_start(p, page_num, lang)

    sig_col_w = (max_width - 30) / 2
    for i, label in enumerate((L["client_signature"], L["contractor_signature"])):
        x = MARGIN + i * (sig_col_w + 30)
        p.line(x, y, x + sig_col_w, y)
        p.setFont("Helvetica", 9)
        p.drawString(x, y - 12, label)
        p.line(x, y - 45, x + sig_col_w, y - 45)
        p.drawString(x, y - 57, f"{L['print_name']} / {L['signed_date']}")

    _footer(p, page_num, lang)
    p.save()
    buffer.seek(0)
    return buffer
