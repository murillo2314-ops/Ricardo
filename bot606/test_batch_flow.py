#!/usr/bin/env python3
"""
Prueba offline del flujo de LOTE de facturas (sin red, sin Telegram real).

Simula updates de Telegram con un request falso y verifica:
  A. Lote por menú: las N fotos enviadas se ACUMULAN en el lote (no se
     reinicia la conversación por el entry point con allow_reentry).
  B. Álbum directo (media_group_id): se procesa como lote automático.
  C. Los textos con Markdown escapan los caracteres especiales del nombre
     del proveedor (evita BadRequest: Can't parse entities).

Uso:  python test_batch_flow.py
"""

import asyncio
import itertools
import json
import os
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Config de entorno ANTES de importar bot.py
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TESTTOKEN")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
_tmpdb = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmpdb.close()
os.environ["DB_PATH"] = _tmpdb.name

import bot  # noqa: E402

from telegram import Update  # noqa: E402
from telegram.ext import ExtBot  # noqa: E402
from telegram.request import BaseRequest  # noqa: E402

UID = 111  # chat privado: chat_id == user_id


# ──────────────────────────────────────────────────────────────
# Bot API falsa
# ──────────────────────────────────────────────────────────────

class FakeRequest(BaseRequest):
    """Responde localmente a los métodos de la Bot API que usa el flujo."""

    def __init__(self):
        self._next_id = itertools.count(1000)
        self.last_message_id = None
        self.calls = []  # (metodo, params)

    async def initialize(self):
        pass

    async def shutdown(self):
        pass

    def _message(self, params):
        mid = params.get("message_id") or next(self._next_id)
        self.last_message_id = mid
        return {
            "message_id": mid,
            "date": int(time.time()),
            "chat": {"id": int(params.get("chat_id", UID)),
                     "type": "private", "first_name": "Ricardo"},
            "from": {"id": 42, "is_bot": True, "first_name": "Gabi"},
            "text": params.get("text", ""),
        }

    async def do_request(self, url, method, request_data=None,
                         read_timeout=None, write_timeout=None,
                         connect_timeout=None, pool_timeout=None):
        # Descarga de archivos (retrieve)
        if "/file/bot" in url:
            return 200, b"FAKEIMGDATA"

        api = url.rsplit("/", 1)[-1]
        params = dict(request_data.parameters) if request_data else {}
        self.calls.append((api, params))

        if api == "getMe":
            result = {"id": 42, "is_bot": True, "first_name": "Gabi",
                      "username": "gabi_bot",
                      "can_join_groups": True,
                      "can_read_all_group_messages": False,
                      "supports_inline_queries": False}
        elif api in ("sendMessage", "editMessageText"):
            result = self._message(params)
        elif api == "getFile":
            result = {"file_id": params["file_id"],
                      "file_unique_id": "u" + str(params["file_id"]),
                      "file_path": "photos/fake.jpg"}
        elif api in ("answerCallbackQuery", "deleteMessage", "deleteWebhook"):
            result = True
        else:
            result = True
        return 200, json.dumps({"ok": True, "result": result}).encode()


# ──────────────────────────────────────────────────────────────
# Fabricar updates
# ──────────────────────────────────────────────────────────────

_upd_id = itertools.count(1)
_msg_id = itertools.count(1)


def _user():
    return {"id": UID, "is_bot": False, "first_name": "Ricardo"}


def _chat():
    return {"id": UID, "type": "private", "first_name": "Ricardo"}


def upd_text(text):
    return {"update_id": next(_upd_id),
            "message": {"message_id": next(_msg_id), "date": int(time.time()),
                        "chat": _chat(), "from": _user(), "text": text}}


def upd_photo(fid, media_group=None):
    msg = {"message_id": next(_msg_id), "date": int(time.time()),
           "chat": _chat(), "from": _user(),
           "photo": [{"file_id": fid, "file_unique_id": "u" + fid,
                      "width": 800, "height": 600}]}
    if media_group:
        msg["media_group_id"] = media_group
    return {"update_id": next(_upd_id), "message": msg}


def upd_pdf(fid, name="facturas.pdf"):
    return {"update_id": next(_upd_id),
            "message": {"message_id": next(_msg_id), "date": int(time.time()),
                        "chat": _chat(), "from": _user(),
                        "document": {"file_id": fid,
                                     "file_unique_id": "u" + fid,
                                     "file_name": name,
                                     "mime_type": "application/pdf"}}}


def upd_cq(data, message_id):
    return {"update_id": next(_upd_id),
            "callback_query": {
                "id": str(next(_upd_id)), "from": _user(),
                "chat_instance": "ci-1", "data": data,
                "message": {"message_id": message_id, "date": int(time.time()),
                            "chat": _chat(),
                            "from": {"id": 42, "is_bot": True,
                                     "first_name": "Gabi"},
                            "text": "x"}}}


# ──────────────────────────────────────────────────────────────
# Stub de extracción con IA (sin API)
# ──────────────────────────────────────────────────────────────

_ncf_n = itertools.count(1)


async def fake_extract(image_bytes, filename):
    n = next(_ncf_n)
    return {
        "_filename": filename, "_error": None,
        "nombre_proveedor": f"PROVEEDOR {n}",
        "rnc": "101000001", "ncf": f"B01000000{n:02d}",
        "fecha_comprobante": "2026-06-15",
        "monto_sin_itbis": 100.0, "itbis": 18.0, "propina": 0.0,
        "total_facturado": 118.0, "metodo_pago": "EFECTIVO",
        "nivel_confianza": "ALTO", "observaciones": "",
        "_qr_verified": False, "_warnings": [], "_needs_review": False,
    }


# ──────────────────────────────────────────────────────────────
# Escenarios
# ──────────────────────────────────────────────────────────────

FAILS = []


def check(cond, label):
    mark = "OK " if cond else "FALLO"
    print(f"  [{mark}] {label}")
    if not cond:
        FAILS.append(label)


async def run():
    bot.extract_invoice = fake_extract
    bot.init_db()

    fake = FakeRequest()
    tbot = ExtBot(token=os.environ["TELEGRAM_BOT_TOKEN"],
                  request=fake, get_updates_request=FakeRequest())
    app = bot.build_application(bot=tbot)
    conv = app.handlers[0][0]

    await app.initialize()

    async def drive(data):
        await app.process_update(Update.de_json(data, app.bot))

    def state():
        return conv._conversations.get((UID, UID))

    ud = app.user_data[UID]

    # Desbloquear con la contraseña
    await drive(upd_text(bot.BOT_PASSWORD))
    check(ud.get("unlocked") is True, "contraseña desbloquea el bot")

    print("\n— Escenario A: lote por menú, álbum de 3 fotos —")
    await drive(upd_text(bot.BTN_NUEVA))
    check(state() == bot.S_MODE, "menú de modo (S_MODE)")
    await drive(upd_cq("mode_batch", fake.last_message_id))
    check(state() == bot.S_LOCATION, "lote → pregunta ubicación")
    await drive(upd_cq(f"loc_{bot.LOCATIONS[0]}", fake.last_message_id))
    await drive(upd_cq(f"cat_{bot.CATEGORIES[0]}", fake.last_message_id))
    check(state() == bot.S_COLLECT, "categoría → recolectando (S_COLLECT)")

    for i in range(1, 4):
        await drive(upd_photo(f"A{i}", media_group="ALBUM1"))
    ids = ud.get("batch_photo_ids") or []
    check(len(ids) == 3,
          f"las 3 fotos del álbum quedan en el lote (hay {len(ids)})")
    check(state() == bot.S_COLLECT,
          f"sigue recolectando, no se reinició (estado={state()})")

    await drive(upd_cq("batch_done", fake.last_message_id))
    items = ud.get("batch_items") or []
    check(len(items) == 3, f"lote procesado con 3 facturas (hay {len(items)})")
    check(state() == bot.S_BATCH_LIST, "lista del lote (S_BATCH_LIST)")

    # Revisar la #2, aceptarla desde la tarjeta, aceptar el resto
    await drive(upd_cq("brev_1", fake.last_message_id))
    check(state() == bot.S_CONFIRM, "🔍 Revisar abre la tarjeta (S_CONFIRM)")
    await drive(upd_cq("bconf_accept", fake.last_message_id))
    check(state() == bot.S_BATCH_LIST, "aceptar desde tarjeta vuelve a la lista")
    await drive(upd_cq("baccall", fake.last_message_id))
    guardadas = bot.get_facturas("2026-06")
    check(len(guardadas) == 3,
          f"las 3 facturas quedaron guardadas en 2026-06 (hay {len(guardadas)})")
    check(state() is None, "lote terminado cierra la conversación")

    print("\n— Escenario B: álbum directo (sin menú) —")
    for i in range(1, 4):
        await drive(upd_photo(f"B{i}", media_group="ALBUM2"))
    ids = ud.get("batch_photo_ids") or []
    check(ud.get("mode") == "batch_photo", "álbum directo entra en modo lote")
    check(len(ids) == 3, f"las 3 fotos del álbum acumuladas (hay {len(ids)})")
    check(state() == bot.S_LOCATION, "pregunta ubicación una sola vez")
    await drive(upd_cq(f"loc_{bot.LOCATIONS[1]}", fake.last_message_id))
    await drive(upd_cq(f"cat_{bot.CATEGORIES[1]}", fake.last_message_id))
    check(state() == bot.S_COLLECT, "pasa a recolectar con las fotos ya contadas")
    await drive(upd_cq("batch_done", fake.last_message_id))
    items = ud.get("batch_items") or []
    check(len(items) == 3, f"lote del álbum procesado (hay {len(items)})")
    await drive(upd_cq("baccall", fake.last_message_id))
    guardadas = bot.get_facturas("2026-06")
    check(len(guardadas) == 6,
          f"total 6 facturas guardadas (hay {len(guardadas)})")

    print("\n— Escenario D: foto individual (sin álbum) —")
    await drive(upd_photo("SOLO1"))  # sin media_group_id
    check(ud.get("mode") == "single", "foto suelta entra en modo individual")
    check(state() == bot.S_LOCATION, "pregunta ubicación de la compra")
    await drive(upd_cq(f"loc_{bot.LOCATIONS[0]}", fake.last_message_id))
    await drive(upd_cq(f"cat_{bot.CATEGORIES[0]}", fake.last_message_id))
    check(state() == bot.S_CONFIRM, "muestra la tarjeta de revisión")
    await drive(upd_cq("confirm_accept", fake.last_message_id))
    guardadas = bot.get_facturas("2026-06")
    check(len(guardadas) == 7,
          f"la factura individual quedó guardada (hay {len(guardadas)})")
    await drive(upd_cq("fin_lote", fake.last_message_id))
    check(state() is None, "Terminar cierra la conversación")

    print("\n— Escenario E: PDF directo (1 factura por página) —")
    bot.render_pdf_pages = lambda pdf_bytes, **kw: [b"PG1", b"PG2"]
    await drive(upd_pdf("PDF1"))
    check(ud.get("mode") == "batch_pdf", "PDF directo entra en modo lote PDF")
    check(state() == bot.S_LOCATION, "PDF → pregunta ubicación")
    await drive(upd_cq(f"loc_{bot.LOCATIONS[1]}", fake.last_message_id))
    await drive(upd_cq(f"cat_{bot.CATEGORIES[1]}", fake.last_message_id))
    items = ud.get("batch_items") or []
    check(len(items) == 2,
          f"2 páginas del PDF procesadas como facturas (hay {len(items)})")
    check(state() == bot.S_BATCH_LIST, "lista del lote PDF (S_BATCH_LIST)")
    await drive(upd_cq("baccall", fake.last_message_id))
    guardadas = bot.get_facturas("2026-06")
    check(len(guardadas) == 9,
          f"total 9 facturas guardadas (hay {len(guardadas)})")

    print("\n— Escenario F: fechas en formato latino (DD/MM/AAAA) —")
    nf = bot.normalize_fecha
    check(nf("15/06/2026") == "2026-06-15", "acepta DD/MM/AAAA")
    check(nf("15-06-2026") == "2026-06-15", "acepta DD-MM-AAAA")
    check(nf("5/6/26") == "2026-06-05", "acepta D/M/AA")
    check(nf("2026-06-15") == "2026-06-15", "ISO pasa igual")
    check(nf("31/02/x") == "" and nf("ayer") == "", "basura no pasa")
    check(bot.fecha_display("2026-06-15") == "15/06/2026",
          "se muestra como 15/06/2026")
    vf = bot.validate_and_fix({"_error": None, "fecha_comprobante": "15/06/2026",
                               "total_facturado": 118, "itbis": 18,
                               "monto_sin_itbis": 100, "rnc": "101000001",
                               "ncf": "B0100000099"})
    check(vf["fecha_comprobante"] == "2026-06-15",
          "validate_and_fix normaliza fecha latina de la IA")

    # Flujo real: corregir la fecha escribiéndola en formato latino
    await drive(upd_photo("FCHA1"))
    await drive(upd_cq(f"loc_{bot.LOCATIONS[0]}", fake.last_message_id))
    await drive(upd_cq(f"cat_{bot.CATEGORIES[0]}", fake.last_message_id))
    await drive(upd_cq("confirm_edit", fake.last_message_id))
    await drive(upd_cq("edit_fecha", fake.last_message_id))
    await drive(upd_text("no-es-fecha"))
    check(state() == bot.S_EDIT_VALUE,
          "fecha inválida se rechaza y sigue pidiendo el valor")
    await drive(upd_text("20/06/2026"))
    data = ud.get("pending_invoice") or {}
    check(data.get("fecha_comprobante") == "2026-06-20",
          "fecha editada '20/06/2026' queda ISO internamente")
    check(state() == bot.S_CONFIRM, "vuelve a la tarjeta de revisión")
    card_params = [p for a, p in fake.calls
                   if a == "sendMessage" and "Fecha" in p.get("text", "")][-1]
    check("20/06/2026" in card_params["text"],
          "la tarjeta muestra la fecha en formato latino")
    await drive(upd_cq("confirm_accept", fake.last_message_id))
    check(len(bot.get_facturas("2026-06")) == 10,
          "quedó guardada en el mes correcto (2026-06)")
    await drive(upd_cq("fin_lote", fake.last_message_id))

    print("\n— Escenario C: escape de Markdown —")
    nombre_feo = "FERRE_MAX *SRL* [STO DGO]"
    check(hasattr(bot, "md"), "existe helper bot.md() de escape")
    if hasattr(bot, "md"):
        esc = bot.md(nombre_feo)
        check("\\_" in esc and "\\*" in esc and "\\[" in esc,
              "md() escapa _ * [")
        card = bot.format_review_message(
            {"nombre_proveedor": nombre_feo, "ncf": "B0100000001",
             "rnc": "101000001", "fecha_comprobante": "2026-06-15",
             "monto_sin_itbis": 100, "itbis": 18, "propina": 0,
             "total_facturado": 118, "metodo_pago": "EFECTIVO",
             "nivel_confianza": "ALTO"},
            "Punta Cana", "Casa", "2026-06", "02")
        check("FERRE\\_MAX" in card,
              "la tarjeta de revisión escapa el nombre del proveedor")

    await app.shutdown()

    print()
    if FAILS:
        print(f"❌ {len(FAILS)} verificación(es) fallaron:")
        for f in FAILS:
            print(f"   - {f}")
        return 1
    print("✅ Todas las verificaciones pasaron.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
