"""
Fill the ProAstra KYC PDF by overlaying text at exact coordinates
derived from the PDF content stream analysis.
"""
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter

# Exact y-positions extracted from PDF text blocks.
# x-positions computed from label character widths at ~9pt Helvetica.
FIELDS = [
    # PERSONAL INFORMATION  (y row = 682.78)
    ("Ricardo Daniel Murillo Rojas",   84,  682.78),
    ("402-4797942-6",                 364,  682.78),

    # Date of Birth / Nationality  (y = 658.03)
    ("27 de Julio, 2001",              94,  658.03),
    ("Dominicana",                    358,  658.03),

    # Marital Status / Profession  (y = 633.07)
    ("Soltero",                       100,  633.07),
    ("Ing. Supervisor de Obra / Ing. de Campo", 358, 633.07),

    # Gender  (y = 608.35)
    ("Masculino",                      72,  608.35),

    # CONTACT INFORMATION
    # Phone / Emergency Phone  (y = 533.93)
    ("+1 (829) 546-0075",              68,  533.93),
    ("(829) 546-0075 / (809) 645-0075", 389, 533.93),

    # Email / Address  (y = 508.94)
    ("murillo2314@gmail.com",           65,  508.94),
    ("Melvin Jones #157, Sto. Domingo, R.D.", 347, 508.94),

    # EMPLOYMENT
    # Company / Position  (y = 434.54)
    ("Inversiones Romur, SRL  (RNC: 131-54515-7)", 81, 434.54),
    ("Ing. Supervisor de Obra",        347,  434.54),

    # Company Phone / Monthly Income  (y = 409.56)
    ("r.murillo@inversionesromur.com", 114,  409.56),
    ("RD$ 95,000.00",                  380,  409.56),

    # FINANCIAL
    # Bank Account / Bank  (y = 335.14)
    ("Cta. Corriente No. 809222524",   102,  335.14),
    ("Banco Popular Dominicano",       333,  335.14),

    # Proof of Income  (y = 310.18)
    ("Carta Laboral (a entregar aparte)", 110, 310.18),

    # DECLARATION
    # Acting for third party / PEP  (y = 235.75)
    ("No",                            131,  235.75),
    ("No",                            329,  235.75),

    # Notes  (y = 211.03)
    ("—",                              66,  211.03),

    # SIGNATURE
    # Client signature / Realtor Name  (y = 136.37)
    ("Ricardo Daniel Murillo Rojas",  108,  136.37),
]

def create_overlay():
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.1, 0.1, 0.6)   # subtle blue, clean professional look

    for value, x, y in FIELDS:
        c.drawString(x, y, value)

    c.save()
    packet.seek(0)
    return packet


original = PdfReader("/root/.claude/uploads/0d02e5e2-ce91-4400-86cb-d3f06e9edb35/be5a81df-KYC_ProAstra_.pdf")
overlay_pdf = PdfReader(create_overlay())

writer = PdfWriter()
page = original.pages[0]
page.merge_page(overlay_pdf.pages[0])
writer.add_page(page)

output = "/home/user/Ricardo/KYC_Ricardo_Murillo_ProAstra.pdf"
with open(output, "wb") as f:
    writer.write(f)

print(f"PDF listo: {output}")
