"""
Fill the ProAstra KYC PDF by overlaying text at coordinates computed
from the PDF content stream.

Scale factor 1.200 is derived from the only directly measurable label:
  "Client signature " → underscores start at x=112.85, label starts at x=36.024
  → actual label width = 76.83 pt
  → Helvetica 9pt AFM width = 64.03 pt
  → scale = 76.83 / 64.03 = 1.200
"""
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter

# Computed from AFM widths × 9pt × scale(1.200), GAP = 4pt after label end.
# Format: (value_text, x, y)
# y-coordinates are exact from PDF content stream parse.
# Declaration section intentionally left blank as requested.
FIELDS = [
    # ── PERSONAL INFORMATION ─────────────────────────────────
    # Full Name / ID  (y=682.78)
    ("Ricardo Daniel Murillo Rojas",           93, 682.78),
    ("402-4797942-6",                         375, 682.78),

    # Date of Birth / Nationality  (y=658.03)
    ("27 de Julio, 2001",                     104, 658.03),
    ("Dominicana",                            363, 658.03),

    # Marital Status / Profession  (y=633.07)
    ("Soltero",                               109, 633.07),
    ("Ing. Supervisor de Obra / Ing. Campo",  363, 633.07),

    # Gender  (y=608.35)
    ("Masculino",                              80, 608.35),

    # ── CONTACT INFORMATION ──────────────────────────────────
    # Phone / Emergency Phone  (y=533.93)
    ("+1 (829) 546-0075",                      75, 533.93),
    ("(829) 546-0075 / (809) 645-0075",       401, 533.93),

    # Email / Address  (y=508.94)
    ("murillo2314@gmail.com",                  71, 508.94),
    ("Melvin Jones #157, Sto. Domingo, R.D.", 353, 508.94),

    # ── EMPLOYMENT ───────────────────────────────────────────
    # Company / Position  (y=434.54)
    ("Inversiones Romur, SRL (RNC: 131-54515-7)", 90, 434.54),
    ("Ing. Supervisor de Obra",                351, 434.54),

    # Company Phone / Monthly Income  (y=409.56)
    ("r.murillo@inversionesromur.com",         123, 409.56),
    ("RD$ 95,000.00",                          389, 409.56),

    # ── FINANCIAL ────────────────────────────────────────────
    # Bank Account / Bank  (y=335.14)
    ("Cta. Corriente No. 809222524",           111, 335.14),
    ("Banco Popular Dominicano",               338, 335.14),

    # Proof of Income  (y=310.18)
    ("Carta Laboral (a entregar aparte)",      120, 310.18),

    # ── DECLARATION ──────────────────────────────────────────
    # (left blank as requested)

    # ── SIGNATURE ────────────────────────────────────────────
    # Client signature  (y=136.37) — underscores confirmed at x=112.85
    ("Ricardo Daniel Murillo Rojas",           113, 136.37),
]


def create_overlay():
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0, 0, 0)

    for value, x, y in FIELDS:
        c.drawString(x, y, value)

    c.save()
    packet.seek(0)
    return packet


PDF_IN  = "/root/.claude/uploads/0d02e5e2-ce91-4400-86cb-d3f06e9edb35/be5a81df-KYC_ProAstra_.pdf"
PDF_OUT = "/home/user/Ricardo/KYC_Ricardo_Murillo_ProAstra.pdf"

original    = PdfReader(PDF_IN)
overlay_pdf = PdfReader(create_overlay())

writer = PdfWriter()
page = original.pages[0]
page.merge_page(overlay_pdf.pages[0])
writer.add_page(page)

with open(PDF_OUT, "wb") as f:
    writer.write(f)

print(f"PDF listo: {PDF_OUT}")
