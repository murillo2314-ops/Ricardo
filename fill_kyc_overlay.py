import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PyPDF2 import PdfReader, PdfWriter

def create_overlay():
    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    c.setFont("Helvetica", 8.5)
    c.setFillColorRGB(0, 0, 0)

    # ── PERSONAL INFORMATION ──
    c.drawString(155, 649, "Ricardo Daniel Murillo Rojas")
    c.drawString(420, 649, "402-4797942-6")

    c.drawString(155, 629, "27 de Julio, 2001")
    c.drawString(420, 629, "Dominicana")

    c.drawString(155, 609, "Soltero")
    c.drawString(420, 609, "Ing. Supervisor de Obra / Ing. de Campo")

    c.drawString(155, 589, "Masculino")

    # ── CONTACT INFORMATION ──
    c.drawString(110, 525, "+1 (829) 546-0075")
    c.drawString(420, 525, "(829) 546-0075 / (809) 645-0075")

    c.drawString(100, 505, "murillo2314@gmail.com")
    c.drawString(390, 505, "Melvin Jones #157, Sto. Domingo, R.D.")

    # ── EMPLOYMENT ──
    c.drawString(120, 443, "Inversiones Romur, SRL  (RNC: 131-54515-7)")
    c.drawString(390, 443, "Ing. Supervisor de Obra")

    c.drawString(165, 423, "r.murillo@inversionesromur.com")
    c.drawString(390, 423, "RD$ 95,000.00")

    # ── FINANCIAL ──
    c.drawString(145, 361, "Cta. Corriente No. 809222524")
    c.drawString(390, 361, "Banco Popular Dominicano")

    c.drawString(155, 341, "Carta Laboral (a entregar aparte)")

    # ── DECLARATION ──
    c.drawString(185, 279, "No")
    c.drawString(390, 279, "No")

    c.drawString(100, 259, "—")

    # ── SIGNATURE ──
    c.drawString(155, 183, "Ricardo Daniel Murillo Rojas")

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
