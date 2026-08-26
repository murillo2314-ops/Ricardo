from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph

def draw_field(c, label, value, x, y, label_width=120, font_size=9):
    c.setFont("Helvetica-Bold", font_size)
    c.setFillColor(colors.black)
    c.drawString(x, y, label)
    c.setFont("Helvetica", font_size)
    c.setFillColor(colors.HexColor("#1a1a1a"))
    c.drawString(x + label_width, y, value)
    c.setStrokeColor(colors.HexColor("#999999"))
    c.line(x + label_width, y - 2, x + label_width + 190, y - 2)

def draw_section_title(c, title, x, y):
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor("#003366"))
    c.drawString(x, y, title)
    c.setStrokeColor(colors.HexColor("#003366"))
    c.line(x, y - 4, x + 490, y - 4)

def create_kyc_pdf(output_path):
    c = canvas.Canvas(output_path, pagesize=letter)
    width, height = letter  # 612 x 792

    # ── Background ──
    c.setFillColor(colors.white)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    # ── Header ──
    c.setFillColor(colors.HexColor("#003366"))
    c.rect(0, height - 70, width, 70, fill=1, stroke=0)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(width / 2, height - 28, "KYC FORM – PROASTRA REAL ESTATE")
    c.setFont("Helvetica", 9)
    c.drawCentredString(width / 2, height - 45, "Know Your Customer · Formulario de Identificación del Cliente")

    # ── Try to place logo area placeholder ──
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(width - 95, height - 35, "ProAstra")
    c.drawString(width - 95, height - 47, "Real Estate")

    margin_l = 50
    margin_r = width - 50
    col2 = width / 2 + 10
    y = height - 95

    # ════════════════════════════════
    # PERSONAL INFORMATION
    # ════════════════════════════════
    draw_section_title(c, "PERSONAL INFORMATION", margin_l, y)
    y -= 22

    draw_field(c, "Full Name:", "Ricardo Daniel Murillo Rojas", margin_l, y, 90)
    draw_field(c, "ID / Passport:", "402-4797942-6", col2, y, 100)
    y -= 20

    draw_field(c, "Date of Birth:", "27 de Julio, 2001", margin_l, y, 90)
    draw_field(c, "Nationality:", "Dominicana", col2, y, 100)
    y -= 20

    draw_field(c, "Marital Status:", "Soltero", margin_l, y, 90)
    draw_field(c, "Profession:", "Ingeniero Supervisor de Obra / Ing. Campo", col2, y, 100)
    y -= 20

    draw_field(c, "Gender:", "Masculino", margin_l, y, 90)
    y -= 30

    # ════════════════════════════════
    # CONTACT INFORMATION
    # ════════════════════════════════
    draw_section_title(c, "CONTACT INFORMATION", margin_l, y)
    y -= 22

    draw_field(c, "Phone:", "+1 (829) 546-0075", margin_l, y, 90)
    draw_field(c, "Emergency Phone:", "(829) 546-0075 / (809) 645-0075", col2, y, 120)
    y -= 20

    draw_field(c, "Email:", "murillo2314@gmail.com", margin_l, y, 90)
    draw_field(c, "Address:", "Melvin Jones #157, Sto. Domingo, R.D.", col2, y, 100)
    y -= 30

    # ════════════════════════════════
    # EMPLOYMENT
    # ════════════════════════════════
    draw_section_title(c, "EMPLOYMENT", margin_l, y)
    y -= 22

    draw_field(c, "Company:", "Inversiones Romur, SRL  (RNC: 131-54515-7)", margin_l, y, 90)
    draw_field(c, "Position:", "Ing. Supervisor de Obra / Ing. de Campo", col2, y, 100)
    y -= 20

    draw_field(c, "Company Email:", "r.murillo@inversionesromur.com", margin_l, y, 90)
    draw_field(c, "Monthly Income:", "RD$ 95,000.00", col2, y, 100)
    y -= 30

    # ════════════════════════════════
    # FINANCIAL
    # ════════════════════════════════
    draw_section_title(c, "FINANCIAL", margin_l, y)
    y -= 22

    draw_field(c, "Bank Account:", "Cta. Corriente No. 809222524", margin_l, y, 100)
    draw_field(c, "Bank:", "Banco Popular Dominicano", col2, y, 100)
    y -= 20

    draw_field(c, "Proof of Income:", "Carta Laboral (a entregar aparte)", margin_l, y, 100)
    y -= 30

    # ════════════════════════════════
    # DECLARATION
    # ════════════════════════════════
    draw_section_title(c, "DECLARATION", margin_l, y)
    y -= 22

    draw_field(c, "Acting for 3rd party:", "No", margin_l, y, 110)
    draw_field(c, "PEP:", "No", col2, y, 100)
    y -= 20

    draw_field(c, "Notes:", "—", margin_l, y, 90)
    y -= 40

    # ════════════════════════════════
    # SIGNATURE
    # ════════════════════════════════
    draw_section_title(c, "SIGNATURE", margin_l, y)
    y -= 35

    # Signature boxes
    c.setStrokeColor(colors.HexColor("#003366"))
    c.setFillColor(colors.HexColor("#f5f8ff"))
    c.rect(margin_l, y - 40, 220, 45, fill=1, stroke=1)
    c.rect(col2, y - 40, 220, 45, fill=1, stroke=1)

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#666666"))
    c.drawString(margin_l + 5, y - 35, "Client Signature")
    c.drawString(col2 + 5, y - 35, "Realtor Name / Signature")

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor("#003366"))
    c.drawString(margin_l + 5, y - 50, "Ricardo Daniel Murillo Rojas")

    y -= 60

    # ── Footer ──
    c.setFillColor(colors.HexColor("#003366"))
    c.rect(0, 0, width, 30, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica", 7)
    c.drawCentredString(width / 2, 11,
        "ProAstra Real Estate · Documento KYC Confidencial · Uso Interno")

    c.save()
    print(f"PDF generado: {output_path}")

create_kyc_pdf("/home/user/Ricardo/KYC_Ricardo_Murillo_ProAstra.pdf")
