#!/usr/bin/env python3
"""
auth_build.py — Flujo PKCE manual (sin client secret) + creacion de la playlist.

Dos pasos:
  python auth_build.py url --client-id XXXX
      -> imprime el link de autorizacion y guarda el code_verifier en .verifier

  python auth_build.py finish "<redirect_url_pegada>" --client-id XXXX
      -> intercambia el code por token, resuelve el tracklist y crea la playlist

Usa raw requests para controlar la persistencia del verifier entre procesos.
Reutiliza la logica de resolucion de tracks de build_playlist.py.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
import secrets
import sys
import urllib.parse
from pathlib import Path

import requests

from build_playlist import (
    URI_HINTS_BY_TITLE,
    chunked,
    normalize,
    read_tracklist,
    score_match,
)

HERE = Path(__file__).resolve().parent
VERIFIER_FILE = HERE / ".verifier"
REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPE = "playlist-modify-private playlist-modify-public"
PLAYLIST_NAME = os.environ.get("PLAYLIST_NAME", "Trippy Trip")
PLAYLIST_DESCRIPTION = (
    "DJ set techno/hard techno 120-140 BPM - warm-up a hard peak a cierre - trippy"
)
AUTH = "https://accounts.spotify.com"
API = "https://api.spotify.com/v1"


def make_url(client_id: str) -> str:
    verifier = secrets.token_urlsafe(64)
    VERIFIER_FILE.write_text(verifier, encoding="utf-8")
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "code_challenge_method": "S256",
        "code_challenge": challenge,
        "state": secrets.token_urlsafe(8),
    }
    return f"{AUTH}/authorize?" + urllib.parse.urlencode(params)


def exchange_code(client_id: str, redirect_url: str) -> str:
    if not VERIFIER_FILE.exists():
        sys.exit("No hay .verifier; corre primero el paso 'url'.")
    verifier = VERIFIER_FILE.read_text(encoding="utf-8").strip()
    qs = urllib.parse.urlparse(redirect_url).query
    code = urllib.parse.parse_qs(qs).get("code", [None])[0]
    if not code:
        sys.exit("No encontre 'code' en la URL que pegaste.")
    resp = requests.post(
        f"{AUTH}/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "code_verifier": verifier,
        },
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def resolve(token: str, title: str, artist: str) -> tuple[str | None, str]:
    hint = URI_HINTS_BY_TITLE.get(normalize(title))
    if hint:
        return hint, f"{title} - {artist} (hint)"
    r = requests.get(
        f"{API}/search",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": f"{title} {artist}", "type": "track", "limit": 5},
        timeout=20,
    )
    r.raise_for_status()
    items = r.json().get("tracks", {}).get("items", [])
    if not items:
        return None, f"{title} - {artist} (SIN RESULTADOS)"
    best = max(items, key=lambda it: score_match(title, artist, it))
    got = ", ".join(a["name"] for a in best["artists"])
    return best["uri"], f"{best['name']} - {got}"


def build(token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"}
    tracks = read_tracklist()
    uris, missing = [], []
    for i, (title, artist) in enumerate(tracks, 1):
        uri, label = resolve(token, title, artist)
        if uri:
            uris.append(uri)
            print(f"  {i:2d}. OK    {label}")
        else:
            missing.append(label)
            print(f"  {i:2d}. FALTA {label}")
    print(f"\nResueltas {len(uris)}/{len(tracks)}.")
    if missing:
        print("Faltantes:")
        for m in missing:
            print("   -", m)
    if not uris:
        sys.exit("Nada que subir.")

    me = requests.get(f"{API}/me", headers=headers, timeout=20).json()
    pl = requests.post(
        f"{API}/users/{me['id']}/playlists",
        headers=headers,
        json={"name": PLAYLIST_NAME, "public": False, "description": PLAYLIST_DESCRIPTION},
        timeout=20,
    ).json()
    for batch in chunked(uris, 100):
        rr = requests.post(
            f"{API}/playlists/{pl['id']}/tracks",
            headers=headers,
            json={"uris": batch},
            timeout=20,
        )
        rr.raise_for_status()
    print(f"\nOK: '{PLAYLIST_NAME}' creada con {len(uris)} canciones en orden.")
    print("  " + pl["external_urls"]["spotify"])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("step", choices=["url", "finish"])
    p.add_argument("redirect_url", nargs="?", default="")
    p.add_argument("--client-id", default=os.environ.get("SPOTIPY_CLIENT_ID", ""))
    a = p.parse_args()
    if not a.client_id:
        sys.exit("Falta --client-id (o SPOTIPY_CLIENT_ID).")

    if a.step == "url":
        print(make_url(a.client_id))
    else:
        token = exchange_code(a.client_id, a.redirect_url)
        build(token)


if __name__ == "__main__":
    main()
