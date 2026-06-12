#!/usr/bin/env python3
"""
Bot 606 DGII — Telegram con flujo guiado por botones.
"""

import asyncio
import base64
import io
import json
import logging
import os
import re
import sqlite3
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import anthropic
from dotenv import load_dotenv
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

BOT_TOKEN     = os.environ["TELEGRAM_BOT_TOKEN"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
DB_PATH       = os.environ.get("DB_PATH", "/data/facturas.db")

ALLOWED_USERS_ENV = os.environ.get("ALLOWED_USERS", "")
ALLOWED_USERS = set(
    int(x.strip()) for x in ALLOWED_USERS_ENV.split(",") if x.strip().isdigit()
)

(
    S_LOCATION,
    S_CATEGORY,
    S_PHOTO,
    S_CONFIRM,
    S_EDIT_SELECT,
    S_EDIT_VALUE,
) = range(6)

LOCATIONS   = ["Punta Cana", "Santo Domingo"]
CATEGORIES  = ["Casa", "Obra"]

EDITABLE_FIELDS = {
    "total":    "\U0001f4b0 Total",
    "itbis":    "\U0001f9fe ITBIS",
    "base":     "\U0001f4e6 Base",
    "propina":  "\U0001f37d️ Propina",
    "ncf":      "\U0001f522 NCF",
    "rnc":      "\U0001f3e2 RNC",
    "nombre":   "\U0001f3ea Nombre proveedor",
    "fecha":    "\U0001f4c5 Fecha",
    "metodo":   "\U0001f4b3 Método pago",
    "obs":      "\U0001f4dd Observaciones",
}

METODO_LABELS = {
    "EFECTIVO":       "\U0001f4b5 Efectivo",
    "TARJETA_CREDITO":"\U0001f4b3 T.Crédito",
    "TARJETA_DEBITO": "\U0001f4b3 T.Débito",
    "TRANSFERENCIA":  "\U0001f3e6 Transfer.",
    "CHEQUE":         "\U0001f4c4 Cheque",
    "CREDITO":        "\U0001f4cb Crédito",
}

def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True) if '/' in DB_PATH else None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS facturas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                mes             TEXT NOT NULL,
                location        TEXT,
                category        TEXT,
                filename        TEXT,
                rnc             TEXT,
                ncf             TEXT,
                nombre          TEXT,
                fecha_comp      TEXT,
                fecha_pago      TEXT,
                total           REAL DEFAULT 0,
                itbis           REAL DEFAULT 0,
                base            REAL DEFAULT 0,
                propina         REAL DEFAULT 0,
                metodo          TEXT,
                tipo_cf         TEXT,
                observaciones   TEXT,
                qr_verified     INTEGER DEFAULT 0,
                nivel_confianza TEXT,
                advertencias    TEXT,
                needs_review    INTEGER DEFAULT 0,
                raw_json        TEXT,
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()

def save_factura(mes, location, category, data):
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO facturas
              (mes, location, category, filename, rnc, ncf, nombre,
               fecha_comp, fecha_pago, total, itbis, base, propina,
               metodo, tipo_cf, observaciones, qr_verified,
               nivel_confianza, advertencias, needs_review, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            mes, location, category,
            data.get("_filename", ""),
            data.get("rnc", ""),
            data.get("ncf", ""),
            data.get("nombre_proveedor", ""),
            data.get("fecha_comprobante", ""),
            data.get("fecha_pago", ""),
            float(data.get("total_facturado") or 0),
            float(data.get("itbis") or 0),
            float(data.get("monto_sin_itbis") or 0),
            float(data.get("propina") or 0),
            data.get("metodo_pago", ""),
            data.get("tipo_comprobante", ""),
            data.get("observaciones", ""),
            1 if data.get("_qr_verified") else 0,
            data.get("nivel_confianza", "ALTO"),
            json.dumps(data.get("_warnings") or []),
            1 if data.get("_needs_review") else 0,
            json.dumps(data),
        ))
        conn.commit()
        return cur.lastrowid

def get_facturas(mes):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM facturas WHERE mes=? ORDER BY id", (mes,)
        ).fetchall()
    return [dict(r) for r in rows]

def delete_last(mes):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM facturas WHERE mes=? ORDER BY id DESC LIMIT 1", (mes,)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM facturas WHERE id=?", (row["id"],))
            conn.commit()
            return dict(row)
    return None

EXTRACTION_PROMPT = """Eres un experto en facturación dominicana y fiscalización DGII.

━━━ REGLA DE ORO SOBRE MONTOS ━━━
"total_facturado" = importe FINAL pagado (el número más grande al fondo del ticket).
"itbis"           = monto del ITBIS ya incluido en ese total.
"monto_sin_itbis" = total_facturado − itbis − propina.
NUNCA sumes ITBIS al total — ya está dentro del total.

EJEMPLOS:
• SubTotal 750.00 | ITBIS 135.00 | Propina 75.00 | TOTAL 960.00
  → total=960, itbis=135, propina=75, base=750 ✓
• Total General 6,817.08 | ITBIS 16%=119.85 | ITBIS 18%=246.08
  → total=6817.08, itbis=365.93, base=6451.15 ✓
• Farmacia sin ITBIS: Total 904.80
  → total=904.80, itbis=0, base=904.80 ✓

ITBIS: suma TODAS las tasas (16%+18%) en un solo número.
ISC (seguros/licores): NO es ITBIS — ponlo en observaciones.
PROPINA: 10% solo en restaurantes/bares.
MÉTODO: EFECTIVO | TARJETA_CREDITO | TARJETA_DEBITO | TRANSFERENCIA | CHEQUE | CREDITO
NCF papel: B+2+8 dígitos=11 chars. NCF electrónico: E+2+10 dígitos=13 chars.
TIPO: B01/E31=CREDITO_FISCAL | B02/E32=CONSUMIDOR_FINAL | B14/E34=REGIMEN_ESPECIAL

nivel_confianza: ALTO|MEDIO|BAJO

Responde SOLO con JSON válido, sin markdown:
{\"rnc\":\"\",\"ncf\":\"\",\"fecha_comprobante\":\"YYYY-MM-DD\",\"fecha_pago\":\"YYYY-MM-DD\",
\"total_facturado\":0,\"itbis\":0,\"monto_sin_itbis\":0,\"propina\":0,
\"metodo_pago\":\"\",\"nombre_proveedor\":\"\",\"tipo_comprobante\":\"\",\"observaciones\":null,
\"nivel_confianza\":\"ALTO\"}"""

def decode_qr(image_bytes):
    try:
        import numpy as np
        from PIL import Image
        from pyzbar import pyzbar
        img = Image.open(io.BytesIO(image_bytes))
        for d in pyzbar.decode(np.array(img)):
            return d.data.decode("utf-8", errors="ignore")
    except Exception:
        pass
    try:
        import cv2
        import numpy as np
        from PIL import Image
        img_np = np.array(Image.open(io.BytesIO(image_bytes)).convert("RGB"))
        img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        det = cv2.QRCodeDetector()
        for scale in [1.0, 2.0, 3.0]:
            h, w = img_bgr.shape[:2]
            r = cv2.resize(img_bgr, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_CUBIC)
            data, _, _ = det.detectAndDecode(r)
            if data:
                return data
    except Exception:
        pass
    return None

def parse_ecf_url(qr_text):
    if not qr_text or "ConsultaTimbre" not in qr_text:
        return None
    try:
        params = parse_qs(urlparse(qr_text).query)
        def get(k):
            for key, v in params.items():
                if key.lower() == k.lower(): return v[0]
            return None
        rnc  = re.sub(r"\D", "", get("RNCEmisor") or get("RncEmisor") or "")
        ncf  = (get("ENCF") or "").strip()
        tot  = float((get("MontoTotal") or "0").replace(",", "."))
        fecha = None
        fe = get("FechaEmision")
        if fe:
            try:
                d, m, y = fe.split("-"); fecha = f"{y}-{m}-{d}"
            except Exception:
                pass
        if rnc and ncf and tot:
            return {"rnc": rnc, "ncf": ncf, "total": tot, "fecha": fecha}
    except Exception:
        pass
    return None

def validate_and_fix(data, qr=None):
    if data.get("_error"):
        data["_needs_review"] = True
        data["_warnings"] = ["Error de extracción"]
        return data
    if qr:
        if qr.get("rnc"):   data["rnc"] = qr["rnc"]
        if qr.get("ncf"):   data["ncf"] = qr["ncf"]
        if qr.get("total"): data["total_facturado"] = qr["total"]
        if qr.get("fecha"): data.setdefault("fecha_comprobante", qr["fecha"])
        data["_qr_verified"] = True
    def f(v):
        try: return float(v) if v not in (None, "", "null") else 0.0
        except: return 0.0
    total   = f(data.get("total_facturado"))
    itbis   = f(data.get("itbis"))
    propina = f(data.get("propina"))
    base    = f(data.get("monto_sin_itbis"))
    if total == 0 and (base + itbis) > 0:
        total = base + itbis + propina
    if base == 0 and total > 0:
        base = round(total - itbis - propina, 2)
    data["total_facturado"]  = total
    data["itbis"]            = itbis
    data["propina"]          = propina
    data["monto_sin_itbis"]  = base
    warns = []
    calc = round(base + itbis + propina, 2)
    if abs(calc - total) > 1.0:
        warns.append(f"⚠ Descuadre: {base:.2f}+{itbis:.2f}+{propina:.2f}={calc:.2f} ≠ {total:.2f}")
    rnc = re.sub(r"\D", "", str(data.get("rnc") or ""))
    if len(rnc) not in (9, 11):
        warns.append(f"⚠ RNC '{rnc}' tiene {len(rnc)} dígitos")
    ncf = (data.get("ncf") or "").upper()
    if ncf:
        expected = 11 if ncf.startswith("B") else 13 if ncf.startswith("E") else None
        if expected and len(ncf) != expected:
            warns.append(f"⚠ NCF debería tener {expected} chars (tiene {len(ncf)})")
    if (data.get("nivel_confianza") or "").upper() == "BAJO":
        warns.append("⚠ Imagen poco legible — verificar")
    data["_warnings"]     = warns
    data["_needs_review"] = len(warns) > 0
    return data

async def extract_invoice(image_bytes, filename):
    qr_raw = decode_qr(image_bytes)
    qr     = parse_ecf_url(qr_raw) if qr_raw else None
    hint = ""
    if qr:
        hint = (f"\n\n⚡ QR verificado — usar exactamente:\n"
                f"RNC={qr['rnc']} | NCF={qr['ncf']} | Total={qr['total']}")
        if qr.get("fecha"): hint += f" | Fecha={qr['fecha']}"
    img_b64 = base64.standard_b64encode(image_bytes).decode()
    client  = anthropic.AsyncAnthropic(api_key=ANTHROPIC_KEY)
    try:
        resp = await client.messages.create(
            model="claude-opus-4-8",
            max_tokens=1024,
            system=[{"type": "text", "text": EXTRACTION_PROMPT,
                     "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {
                    "type": "base64", "media_type": "image/jpeg", "data": img_b64}},
                {"type": "text",
                 "text": f"Extrae datos de esta factura ({filename}).{hint}\nResponde solo JSON."},
            ]}],
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:]).removesuffix("```").strip()
        data = json.loads(text)
        data["_filename"] = filename
        data["_error"]    = None
    except json.JSONDecodeError as e:
        data = {"_filename": filename, "_error": f"JSON inválido: {e}"}
    except Exception as e:
        data = {"_filename": filename, "_error": str(e)}
    return validate_and_fix(data, qr)

def format_review_message(data, location, category):
    qr_badge  = "✅ QR verificado" if data.get("_qr_verified") else "\U0001f916 Extraído por IA"
    conf      = data.get("nivel_confianza", "ALTO")
    conf_icon = "\U0001f7e2" if conf == "ALTO" else "\U0001f7e1" if conf == "MEDIO" else "\U0001f534"
    warns     = data.get("_warnings") or []
    metodo    = METODO_LABELS.get(data.get("metodo_pago", ""), data.get("metodo_pago", "—"))
    msg = (
        f"\U0001f9fe *Revisión de factura*\n"
        f"\U0001f4cd {location}  •  \U0001f3f7️ {category}\n"
        f"{qr_badge}  {conf_icon} Confianza: {conf}\n"
        f"{chr(8212)*30}\n"
        f"\U0001f3ea *{data.get('nombre_proveedor') or '—'}*\n"
        f"\U0001f522 NCF: `{data.get('ncf') or '—'}`\n"
        f"\U0001f3e2 RNC: `{data.get('rnc') or '—'}`\n"
        f"\U0001f4c5 Fecha: {data.get('fecha_comprobante') or '—'}\n"
        f"{chr(8212)*30}\n"
        f"\U0001f4e6 Base sin ITBIS:  RD$ *{float(data.get('monto_sin_itbis') or 0):,.2f}*\n"
        f"\U0001f9fe ITBIS:           RD$ *{float(data.get('itbis') or 0):,.2f}*\n"
    )
    if float(data.get("propina") or 0) > 0:
        msg += f"\U0001f37d️ Propina 10%:     RD$ *{float(data.get('propina') or 0):,.2f}*\n"
    msg += (
        f"\U0001f4b0 *TOTAL:          RD$ {float(data.get('total_facturado') or 0):,.2f}*\n"
        f"{chr(8212)*30}\n"
        f"{metodo}\n"
    )
    if data.get("observaciones"):
        msg += f"\U0001f4dd {data['observaciones']}\n"
    if warns:
        msg += f"\n{chr(8212)*30}\n" + "\n".join(warns)
    return msg

def confirm_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Aceptar",  callback_data="confirm_accept"),
        InlineKeyboardButton("✏️ Corregir", callback_data="confirm_edit"),
        InlineKeyboardButton("❌ Cancelar", callback_data="confirm_cancel"),
    ]])

def edit_keyboard():
    buttons = []
    row = []
    for key, label in EDITABLE_FIELDS.items():
        row.append(InlineKeyboardButton(label, callback_data=f"edit_{key}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("↩️ Volver a revisión", callback_data="edit_back")])
    return InlineKeyboardMarkup(buttons)

def current_mes():
    return datetime.now().strftime("%Y-%m")

def get_mes(context):
    return context.user_data.get("mes_activo", current_mes())

def is_allowed(update):
    if not ALLOWED_USERS: return True
    return update.effective_user.id in ALLOWED_USERS

async def start_flow(update, context):
    if not is_allowed(update): return ConversationHandler.END
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"\U0001f4cd {loc}", callback_data=f"loc_{loc}")
        for loc in LOCATIONS
    ]])
    if update.message:
        await update.message.reply_text(
            "\U0001f9fe *Nueva factura*\n\n¿Dónde fue la compra?",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
    return S_LOCATION

async def got_location(update, context):
    query = update.callback_query
    await query.answer()
    location = query.data.replace("loc_", "")
    context.user_data["location"] = location
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(f"\U0001f3f7️ {cat}", callback_data=f"cat_{cat}")
        for cat in CATEGORIES
    ]])
    await query.edit_message_text(
        f"\U0001f4cd *{location}*\n\n¿Para qué es la compra?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return S_CATEGORY

async def got_category(update, context):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data["category"] = category
    location = context.user_data.get("location", "—")
    await query.edit_message_text(
        f"\U0001f4cd *{location}*  •  \U0001f3f7️ *{category}*\n\n"
        f"\U0001f4f8 Envía la foto de la factura ahora.",
        parse_mode="Markdown",
    )
    return S_PHOTO

async def got_photo(update, context):
    if not is_allowed(update): return ConversationHandler.END
    location = context.user_data.get("location", "—")
    category = context.user_data.get("category", "—")
    processing_msg = await update.message.reply_text("⏳ Analizando factura...")
    photo = update.message.photo[-1]
    file  = await context.bot.get_file(photo.file_id)
    buf   = io.BytesIO()
    await file.download_to_memory(buf)
    image_bytes = buf.getvalue()
    data = await extract_invoice(image_bytes, f"{photo.file_id}.jpg")
    await processing_msg.delete()
    if data.get("_error"):
        await update.message.reply_text(
            f"❌ No pude leer la factura: {data['_error']}\n\nIntenta con mejor foto. Usa /nueva para intentar de nuevo.",
        )
        return ConversationHandler.END
    context.user_data["pending_invoice"] = data
    msg = format_review_message(data, location, category)
    await update.message.reply_text(msg, reply_markup=confirm_keyboard(), parse_mode="Markdown")
    return S_CONFIRM

async def confirm_accept(update, context):
    query = update.callback_query
    await query.answer()
    data     = context.user_data.get("pending_invoice", {})
    location = context.user_data.get("location", "—")
    category = context.user_data.get("category", "—")
    mes      = get_mes(context)
    fac_id = save_factura(mes, location, category, data)
    facturas = get_facturas(mes)
    total_mes = sum(f["total"] for f in facturas)
    await query.edit_message_text(
        f"✅ *Factura guardada* #{fac_id}\n\n"
        f"\U0001f3ea {data.get('nombre_proveedor','?')}\n"
        f"\U0001f4b0 RD$ {float(data.get('total_facturado',0)):,.2f}\n\n"
        f"\U0001f4ca *{mes}* — {len(facturas)} facturas  •  Total RD$ {total_mes:,.2f}\n\n"
        f"Usa /nueva para registrar otra o /resumen para ver el mes.",
        parse_mode="Markdown",
    )
    for key in ("pending_invoice", "location", "category", "edit_field"):
        context.user_data.pop(key, None)
    return ConversationHandler.END

async def confirm_cancel(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Factura cancelada. Usa /nueva para empezar de nuevo.")
    for key in ("pending_invoice", "location", "category", "edit_field"):
        context.user_data.pop(key, None)
    return ConversationHandler.END

async def confirm_edit(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "✏️ *¿Qué campo deseas corregir?*\n\nSelecciona el campo:",
        reply_markup=edit_keyboard(),
        parse_mode="Markdown",
    )
    return S_EDIT_SELECT

async def edit_field_selected(update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "edit_back":
        data     = context.user_data.get("pending_invoice", {})
        location = context.user_data.get("location", "—")
        category = context.user_data.get("category", "—")
        msg      = format_review_message(data, location, category)
        await query.edit_message_text(msg, reply_markup=confirm_keyboard(), parse_mode="Markdown")
        return S_CONFIRM
    field = query.data.replace("edit_", "")
    context.user_data["edit_field"] = field
    data  = context.user_data.get("pending_invoice", {})
    label = EDITABLE_FIELDS.get(field, field)
    current_values = {
        "total":   f"RD$ {float(data.get('total_facturado',0)):,.2f}",
        "itbis":   f"RD$ {float(data.get('itbis',0)):,.2f}",
        "base":    f"RD$ {float(data.get('monto_sin_itbis',0)):,.2f}",
        "propina": f"RD$ {float(data.get('propina',0)):,.2f}",
        "ncf":     data.get("ncf",""),
        "rnc":     data.get("rnc",""),
        "nombre":  data.get("nombre_proveedor",""),
        "fecha":   data.get("fecha_comprobante",""),
        "metodo":  data.get("metodo_pago",""),
        "obs":     data.get("observaciones",""),
    }
    metodo_hint = ""
    if field == "metodo":
        metodo_hint = ("\n\nOpciones válidas:\n"
                       "EFECTIVO | TARJETA_CREDITO | TARJETA_DEBITO\n"
                       "TRANSFERENCIA | CHEQUE | CREDITO")
    await query.edit_message_text(
        f"✏️ *Corregir: {label}*\n\n"
        f"Valor actual: `{current_values.get(field,'—')}`\n\n"
        f"Escribe el nuevo valor:{metodo_hint}",
        parse_mode="Markdown",
    )
    return S_EDIT_VALUE

async def edit_value_received(update, context):
    if not is_allowed(update): return ConversationHandler.END
    field    = context.user_data.get("edit_field")
    new_val  = update.message.text.strip()
    data     = context.user_data.get("pending_invoice", {})
    location = context.user_data.get("location", "—")
    category = context.user_data.get("category", "—")
    try:
        if field == "total":
            data["total_facturado"] = float(new_val.replace(",", ".").replace("RD$", "").strip())
        elif field == "itbis":
            data["itbis"] = float(new_val.replace(",", ".").replace("RD$", "").strip())
        elif field == "base":
            data["monto_sin_itbis"] = float(new_val.replace(",", ".").replace("RD$", "").strip())
        elif field == "propina":
            data["propina"] = float(new_val.replace(",", ".").replace("RD$", "").strip())
        elif field == "ncf":
            data["ncf"] = new_val.upper()
        elif field == "rnc":
            data["rnc"] = re.sub(r"\D", "", new_val)
        elif field == "nombre":
            data["nombre_proveedor"] = new_val.upper()
        elif field == "fecha":
            data["fecha_comprobante"] = new_val
        elif field == "metodo":
            data["metodo_pago"] = new_val.upper()
        elif field == "obs":
            data["observaciones"] = new_val
    except ValueError:
        await update.message.reply_text(
            f"⚠️ Valor inválido: `{new_val}`\nEscribe un número válido.",
            parse_mode="Markdown",
        )
        return S_EDIT_VALUE
    if field in ("total", "itbis", "base", "propina"):
        total   = float(data.get("total_facturado") or 0)
        itbis   = float(data.get("itbis") or 0)
        propina = float(data.get("propina") or 0)
        base    = float(data.get("monto_sin_itbis") or 0)
        if field in ("total", "itbis"):
            base = round(total - itbis - propina, 2)
            data["monto_sin_itbis"] = base
        warns = []
        calc = round(base + itbis + propina, 2)
        if abs(calc - total) > 1.0:
            warns.append(f"⚠ Descuadre: {base:.2f}+{itbis:.2f}+{propina:.2f}={calc:.2f} ≠ {total:.2f}")
        existing = [w for w in (data.get("_warnings") or []) if "Descuadre" not in w]
        data["_warnings"] = existing + warns
        data["_needs_review"] = len(data["_warnings"]) > 0
    context.user_data["pending_invoice"] = data
    context.user_data.pop("edit_field", None)
    msg = format_review_message(data, location, category)
    await update.message.reply_text(msg, reply_markup=confirm_keyboard(), parse_mode="Markdown")
    return S_CONFIRM

async def conv_cancel(update, context):
    for key in ("pending_invoice", "location", "category", "edit_field"):
        context.user_data.pop(key, None)
    if update.message:
        await update.message.reply_text("Operación cancelada. Usa /nueva para empezar.")
    return ConversationHandler.END

async def cmd_start(update, context):
    if not is_allowed(update): return
    mes = get_mes(context)
    await update.message.reply_text(
        f"\U0001f44b *Bot 606 DGII*\n\n"
        f"Mes activo: *{mes}*\n\n"
        f"*Registrar facturas:*\n"
        f"\U0001f195 /nueva — capturar factura (flujo guiado)\n\n"
        f"*Consultas:*\n"
        f"\U0001f4ca /resumen — totales del mes\n"
        f"\U0001f4cb /lista — todas las facturas\n"
        f"⚠️ /pendientes — facturas con advertencias\n"
        f"\U0001f4e5 /exportar — descargar Excel 606\n"
        f"\U0001f5d1 /borrar — eliminar última factura\n"
        f"\U0001f4c5 /mes YYYY-MM — cambiar mes activo",
        parse_mode="Markdown",
    )

async def cmd_resumen(update, context):
    if not is_allowed(update): return
    mes = get_mes(context)
    facturas = get_facturas(mes)
    if not facturas:
        await update.message.reply_text(f"Sin facturas para *{mes}*.", parse_mode="Markdown")
        return
    total  = sum(f["total"]   for f in facturas)
    itbis  = sum(f["itbis"]   for f in facturas)
    base   = sum(f["base"]    for f in facturas)
    prop   = sum(f["propina"] for f in facturas)
    rev    = sum(1 for f in facturas if f["needs_review"])
    qr_v   = sum(1 for f in facturas if f["qr_verified"])
    by_loc = {}
    by_cat = {}
    for f in facturas:
        loc = f.get("location") or "—"
        cat = f.get("category") or "—"
        by_loc[loc] = by_loc.get(loc, 0) + f["total"]
        by_cat[cat] = by_cat.get(cat, 0) + f["total"]
    loc_lines = "\n".join(f"  \U0001f4cd {k}: RD$ {v:,.2f}" for k, v in sorted(by_loc.items()))
    cat_lines = "\n".join(f"  \U0001f3f7️ {k}: RD$ {v:,.2f}" for k, v in sorted(by_cat.items()))
    await update.message.reply_text(
        f"\U0001f4ca *Resumen {mes}*\n\n"
        f"Facturas: *{len(facturas)}*  •  QR: {qr_v}  •  ⚠️ Revisión: {rev}\n\n"
        f"Base sin ITBIS:  RD$ *{base:,.2f}*\n"
        f"ITBIS:           RD$ *{itbis:,.2f}*\n"
        f"Propina legal:   RD$ *{prop:,.2f}*\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"*TOTAL: RD$ {total:,.2f}*\n\n"
        f"*Por ubicación:*\n{loc_lines}\n\n"
        f"*Por categoría:*\n{cat_lines}",
        parse_mode="Markdown",
    )

async def cmd_lista(update, context):
    if not is_allowed(update): return
    mes = get_mes(context)
    facturas = get_facturas(mes)
    if not facturas:
        await update.message.reply_text(f"Sin facturas para *{mes}*.", parse_mode="Markdown")
        return
    lines = [f"\U0001f4cb *{mes}* — {len(facturas)} facturas\n"]
    for i, f in enumerate(facturas, 1):
        qr  = "✓" if f["qr_verified"] else " "
        rev = "⚠" if f["needs_review"] else " "
        nombre = (f["nombre"] or f["filename"] or "?")[:22]
        lines.append(f"{i:>2}. {qr}{rev} {nombre:<22} RD${f['total']:>9,.2f}")
    text = "\n".join(lines)
    if len(text) > 3800:
        text = text[:3800] + "\n…(usa /exportar para el Excel completo)"
    await update.message.reply_text(f"```\n{text}\n```", parse_mode="Markdown")

async def cmd_pendientes(update, context):
    if not is_allowed(update): return
    mes = get_mes(context)
    facturas = [f for f in get_facturas(mes) if f["needs_review"]]
    if not facturas:
        await update.message.reply_text("✅ Sin advertencias pendientes.")
        return
    lines = [f"⚠️ *Advertencias {mes}*\n"]
    for f in facturas:
        adv = json.loads(f["advertencias"] or "[]")
        lines.append(f"• *{f['nombre'] or f['ncf']}* — RD${f['total']:,.2f}")
        for a in adv:
            lines.append(f"  {a}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def cmd_exportar(update, context):
    if not is_allowed(update): return
    mes = get_mes(context)
    facturas = get_facturas(mes)
    if not facturas:
        await update.message.reply_text(f"Sin facturas para *{mes}*.", parse_mode="Markdown")
        return
    await update.message.reply_text(f"⏳ Generando Excel *{mes}*...", parse_mode="Markdown")
    xlsx = build_excel(facturas, mes)
    await update.message.reply_document(
        document=io.BytesIO(xlsx),
        filename=f"606_{mes}.xlsx",
        caption=f"✅ Formato 606 — {mes} — {len(facturas)} facturas",
    )

async def cmd_borrar(update, context):
    if not is_allowed(update): return
    mes = get_mes(context)
    deleted = delete_last(mes)
    if deleted:
        await update.message.reply_text(
            f"\U0001f5d1 Eliminada: *{deleted['nombre'] or deleted['ncf']}*  RD${deleted['total']:,.2f}",
            parse_mode="Markdown",
        )
    else:
        await update.message.reply_text("No hay facturas para eliminar.")

async def cmd_mes(update, context):
    if not is_allowed(update): return
    args = context.args
    if not args or not re.match(r"^\d{4}-\d{2}$", args[0]):
        await update.message.reply_text("Formato: /mes YYYY-MM  (ej: /mes 2026-06)")
        return
    context.user_data["mes_activo"] = args[0]
    n = len(get_facturas(args[0]))
    await update.message.reply_text(
        f"\U0001f4c5 Mes activo: *{args[0]}* ({n} facturas)", parse_mode="Markdown"
    )

def build_excel(facturas, mes):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    def fill(c): return PatternFill(start_color=c, end_color=c, fill_type="solid")
    def font(bold=False, color="000000", size=9):
        return Font(name="Calibri", bold=bold, color=color, size=size)
    def bdr():
        s = Side(style="thin", color="AAAAAA")
        return Border(left=s, right=s, top=s, bottom=s)
    def aln(h="left", wrap=False):
        return Alignment(horizontal=h, vertical="center", wrap_text=wrap)
    wb = Workbook()
    ws = wb.active
    ws.title = "Formato 606"
    ws.merge_cells("A1:T1")
    c = ws["A1"]
    c.value = f"FORMATO 606 — COMPRAS — {mes}"
    c.font = Font(name="Calibri", bold=True, color="FFFFFF", size=13)
    c.fill = fill("1F4E79")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 28
    ws.merge_cells("A2:T2")
    c = ws["A2"]
    rev = sum(1 for f in facturas if f.get("needs_review"))
    c.value = (f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}  |  "
               f"Facturas: {len(facturas)}  |  Revisión pendiente: {rev}")
    c.font = Font(name="Calibri", italic=True, color="FFFFFF", size=9)
    c.fill = fill("2E75B6")
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 16
    COLS = [
        ("No.",6),("RNC/Cédula",16),("T.ID",5),("Nombre Proveedor",28),
        ("NCF",17),("T.CF",6),("Fec.Comp.",12),("Día\nPago",7),
        ("Base\nSin ITBIS",13),("ITBIS\nFact.",12),("Total\nFact.",13),
        ("Propina\n10%",11),("Mét.\nPago",7),("ITBIS\nRet.",10),
        ("ITBIS\nPerc.",10),("T.Ret\nISR",7),("Mto.\nRenta",11),
        ("Mto.\nServ.",12),("Mto.\nBienes",11),("Observaciones",35),
    ]
    for col, (hdr, w) in enumerate(COLS, 1):
        c = ws.cell(row=3, column=col, value=hdr)
        c.font = font(bold=True, color="FFFFFF")
        c.fill = fill("2E75B6")
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = bdr()
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.row_dimensions[3].height = 32
    totals = dict(base=0.0, itbis=0.0, total=0.0, propina=0.0)
    def tipo_cf(ncf):
        n = (ncf or "").upper()
        if n.startswith(("B01","E31")): return "01"
        if n.startswith(("B02","E32")): return "02"
        if n.startswith(("B14","E34")): return "14"
        if n.startswith(("B11","E41")): return "11"
        return "02"
    def met_code(m):
        m = (m or "").upper()
        if any(x in m for x in ("EFECTIVO","CASH","METALICO","METÁLICO")): return "01"
        if "CHEQUE" in m: return "02"
        if any(x in m for x in ("TRANSFER","DEPOSITO")): return "03"
        if any(x in m for x in ("CREDITO","CRÉDITO","CREDIT")): return "04"
        if any(x in m for x in ("DEBITO","DÉBITO","DEBIT","PIN")): return "05"
        return "01"
    def rnc_tipo(rnc):
        return "2" if len(re.sub(r"\D","",str(rnc or "")))==11 else "1"
    for seq, fac in enumerate(facturas, 1):
        row = seq + 3
        is_qr   = bool(fac.get("qr_verified"))
        needs   = bool(fac.get("needs_review"))
        if is_qr:   rf = fill("E2EFDA")
        elif needs: rf = fill("FFF2CC")
        elif seq%2==0: rf = fill("DEEAF1")
        else: rf = PatternFill()
        rnc   = re.sub(r"\D","",str(fac.get("rnc") or ""))
        total = fac.get("total",0) or 0
        itbis = fac.get("itbis",0) or 0
        base  = fac.get("base",0) or 0
        prop  = fac.get("propina",0) or 0
        if base==0 and total>0:
            base = round(total-itbis-prop, 2)
        totals["base"]    += base
        totals["itbis"]   += itbis
        totals["total"]   += total
        totals["propina"] += prop
        fp = fac.get("fecha_pago") or fac.get("fecha_comp") or ""
        if len(str(fp))==10 and "-" in str(fp):
            fp = str(fp).split("-")[2].lstrip("0") or "0"
        obs = fac.get("observaciones") or ""
        adv = json.loads(fac.get("advertencias") or "[]")
        if adv: obs = (obs+" | "+" | ".join(adv)).strip(" |")
        if is_qr: obs = ("✓ QR. "+obs).strip()
        loc = fac.get("location",""); cat = fac.get("category","")
        if loc or cat:
            tag = f"[{loc}/{cat}]"
            obs = (tag+" "+obs).strip() if obs else tag
        vals = [
            seq, rnc, rnc_tipo(rnc),
            fac.get("nombre",""),
            fac.get("ncf",""),
            tipo_cf(fac.get("ncf","")),
            fac.get("fecha_comp",""),
            fp,
            f"{base:.2f}", f"{itbis:.2f}", f"{total:.2f}", f"{prop:.2f}",
            met_code(fac.get("metodo","")),
            "0.00","0.00","","0.00",
            f"{base:.2f}","0.00",
            obs,
        ]
        CENTER={2,3,5,6,7,8,13,16}; RIGHT={1,9,10,11,12,14,15,17,18,19}
        for col,val in enumerate(vals,1):
            c = ws.cell(row=row, column=col, value=val)
            c.font = font(size=9); c.fill=rf; c.border=bdr()
            if col in CENTER: c.alignment=aln("center")
            elif col in RIGHT: c.alignment=aln("right")
            else: c.alignment=aln("left")
        ws.row_dimensions[row].height=16
    tr = len(facturas)+4
    ws.merge_cells(f"A{tr}:H{tr}")
    c=ws[f"A{tr}"]; c.value="TOTALES"
    c.font=font(bold=True,size=10); c.fill=fill("FFC000")
    c.alignment=Alignment(horizontal="center",vertical="center")
    for off,key in enumerate(["base","itbis","total","propina"]):
        c=ws.cell(row=tr,column=9+off,value=f"{totals[key]:.2f}")
        c.font=font(bold=True,size=10); c.fill=fill("FFC000"); c.alignment=aln("right")
    for col in range(13,21):
        ws.cell(row=tr,column=col).fill=fill("FFC000")
    ws.row_dimensions[tr].height=20
    ws.freeze_panes="A4"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("nueva", start_flow),
            MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, start_flow),
        ],
        states={
            S_LOCATION: [CallbackQueryHandler(got_location, pattern="^loc_")],
            S_CATEGORY: [CallbackQueryHandler(got_category, pattern="^cat_")],
            S_PHOTO:    [MessageHandler(filters.PHOTO, got_photo)],
            S_CONFIRM:  [
                CallbackQueryHandler(confirm_accept, pattern="^confirm_accept$"),
                CallbackQueryHandler(confirm_edit,   pattern="^confirm_edit$"),
                CallbackQueryHandler(confirm_cancel, pattern="^confirm_cancel$"),
            ],
            S_EDIT_SELECT: [CallbackQueryHandler(edit_field_selected, pattern="^edit_")],
            S_EDIT_VALUE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_value_received)],
        },
        fallbacks=[CommandHandler("cancelar", conv_cancel)],
        per_user=True,
        per_chat=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("resumen",    cmd_resumen))
    app.add_handler(CommandHandler("lista",      cmd_lista))
    app.add_handler(CommandHandler("pendientes", cmd_pendientes))
    app.add_handler(CommandHandler("exportar",   cmd_exportar))
    app.add_handler(CommandHandler("borrar",     cmd_borrar))
    app.add_handler(CommandHandler("mes",        cmd_mes))
    log.info("Bot iniciado con flujo guiado.")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
