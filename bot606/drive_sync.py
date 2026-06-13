#!/usr/bin/env python3
"""
Sincronización del Excel 606 con Google Drive.

Usa una cuenta de servicio de Google Cloud. Configurar en Railway:

  GOOGLE_SERVICE_ACCOUNT_JSON  → el JSON completo de la clave de la cuenta
                                 de servicio (pegar tal cual, incluidas llaves).
  GDRIVE_FOLDER_ID             → ID de la carpeta de Drive donde vive el Excel
                                 (compartir esa carpeta con el email de la
                                 cuenta de servicio, permiso Editor).

Si alguna de las dos variables falta, la sincronización queda desactivada y el
bot sigue funcionando normal (solo /exportar manual).
"""

import io
import json
import logging
import os

log = logging.getLogger(__name__)

_SCOPES = ["https://www.googleapis.com/auth/drive"]


def is_configured() -> bool:
    return bool(
        os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        and os.environ.get("GDRIVE_FOLDER_ID")
    )


def _get_service():
    """Build an authenticated Drive API client, or None if not configured."""
    if not is_configured():
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=_SCOPES
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        log.error("No se pudo inicializar Google Drive: %s", e)
        return None


def _find_file(service, folder_id: str, filename: str) -> str | None:
    """Return the file id of `filename` inside `folder_id`, or None."""
    safe = filename.replace("'", "\\'")
    q = (
        f"name = '{safe}' and '{folder_id}' in parents "
        f"and trashed = false"
    )
    resp = (
        service.files()
        .list(q=q, spaces="drive", fields="files(id, name)",
              supportsAllDrives=True, includeItemsFromAllDrives=True)
        .execute()
    )
    files = resp.get("files", [])
    return files[0]["id"] if files else None


def sync_excel(file_bytes: bytes, filename: str) -> str | None:
    """
    Sube o actualiza `filename` en la carpeta de Drive configurada.
    Si ya existe un archivo con ese nombre, reemplaza su contenido (mismo enlace).
    Devuelve el webViewLink, o None si Drive no está configurado o falla.
    """
    service = _get_service()
    if service is None:
        return None

    folder_id = os.environ["GDRIVE_FOLDER_ID"]
    XLSX_MIME = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    try:
        from googleapiclient.http import MediaIoBaseUpload

        media = MediaIoBaseUpload(
            io.BytesIO(file_bytes), mimetype=XLSX_MIME, resumable=False
        )
        existing = _find_file(service, folder_id, filename)

        if existing:
            f = (
                service.files()
                .update(fileId=existing, media_body=media,
                        fields="id, webViewLink", supportsAllDrives=True)
                .execute()
            )
        else:
            meta = {"name": filename, "parents": [folder_id]}
            f = (
                service.files()
                .create(body=meta, media_body=media,
                        fields="id, webViewLink", supportsAllDrives=True)
                .execute()
            )
        return f.get("webViewLink")
    except Exception as e:
        log.error("Fallo al sincronizar con Drive: %s", e)
        return None
