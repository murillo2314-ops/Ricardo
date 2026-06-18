#!/usr/bin/env python3
"""
build_playlist.py — Sube un tracklist EXACTO y ordenado a una playlist de Spotify.

A diferencia del conector "por vibe", esto usa la Spotify Web API oficial para
crear una playlist y añadir las canciones que TÚ quieres, en el orden que quieres.

Uso rápido:
    1) pip install -r requirements.txt
    2) Exporta tus credenciales (ver README.md):
         export SPOTIPY_CLIENT_ID=xxxx
         export SPOTIPY_CLIENT_SECRET=xxxx
         export SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
    3) python build_playlist.py --dry-run      # verifica que encuentra cada track
    4) python build_playlist.py                # crea la playlist de verdad

El tracklist se lee de tracklist.txt (una canción por línea: "Titulo | Artista").
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from pathlib import Path

try:
    import spotipy
    from spotipy.oauth2 import SpotifyPKCE
except ImportError:
    sys.exit("Falta spotipy. Corre:  pip install -r requirements.txt")

HERE = Path(__file__).resolve().parent
TRACKLIST_FILE = HERE / "tracklist.txt"

SCOPE = "playlist-modify-private playlist-modify-public"
DEFAULT_PLAYLIST_NAME = os.environ.get("PLAYLIST_NAME", "Trippy Trip")
PLAYLIST_DESCRIPTION = (
    "DJ set techno/hard techno 120-140 BPM · warm-up → build → peak → "
    "variacion → hard peak → cierre · trippy"
)

# IDs de pista ya confirmados durante la curaduria (resuelven sin depender del
# buscador). La clave es el titulo normalizado. Si editas tracklist.txt y el
# buscador falla en alguno, agrega aqui su ID y vuelve a correr.
URI_HINTS_BY_TITLE = {
    "ghost in my bed": "spotify:track:6Jd3mCgIqpsiQSB26xdq98",
    "blackberries": "spotify:track:1QDpXIgR0U7ta48CwEYBeL",
    "hots 4 u": "spotify:track:5nMrR3Ed99WcQ4Vv0wy8Bf",
    "pressure": "spotify:track:3wdOS1vNOk05bJyV83etSd",
    "medicine": "spotify:track:58sruLTIl39KFsxnD5e7bH",
    "contortion": "spotify:track:4Rkaq3fINcWmZyC7jOENkJ",
    "no fun": "spotify:track:4oCbdqLfEtOvjocPifA2lp",
    "kids": "spotify:track:4CugwiMW8xWd3jo84GbtX7",
    "daydream": "spotify:track:0WsROU8CJrMWBukK5IMs4y",
    "forever melancholia": "spotify:track:6ZWYsvOTYigBYoHMpFOyoA",
    "werewolf disco club": "spotify:track:6iUHeJeetiHa2olRVvtNXE",
    "because they want our seat": "spotify:track:4zr7hfFkbtPBUc9c1CeJN6",
    "girlboss": "spotify:track:04WxwL4ZRewLveO2qjej54",
    "vendetta": "spotify:track:5Y1SndahLemyQ1M9ydCf6N",
    "gipsy queen": "spotify:track:645khgMxKxkXqUEs4UrBB6",
    "legend": "spotify:track:2voOlJ0QcTDTDRexSw6bGe",
    "blackbird sr 71": "spotify:track:4WQ9j1TwdxeMl7OXFKLbws",
    "hands up": "spotify:track:4U4XNkHA99dkqFbOxc8OjL",
    "suck me dry, like a vampire": "spotify:track:1JfwTZbIDXlKUFYbAU3lZx",
    "take it": "spotify:track:14fIlfcmFPlj4V2IazeJ25",
    "rhyme dust": "spotify:track:59QDyqLww2pxyg9ijOPO7f",
    "saving up": "spotify:track:787Y2idwCU2Rk60Prv4wpr",
    "girl": "spotify:track:46N3FCKFABRjNoNBVq4osr",
}


def normalize(text: str) -> str:
    """Minusculas, sin acentos, sin parentesis y espacios colapsados."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"\([^)]*\)", " ", text)        # quita "(... Remix)" para comparar
    text = re.sub(r"[^a-z0-9 ]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def read_tracklist() -> list[tuple[str, str]]:
    """Lee tracklist.txt -> [(titulo, artista), ...]. Ignora vacias y # comentarios."""
    if not TRACKLIST_FILE.exists():
        sys.exit(f"No encuentro {TRACKLIST_FILE.name} junto al script.")
    tracks: list[tuple[str, str]] = []
    for raw in TRACKLIST_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            print(f"  ! Linea sin '|', la salto: {line}")
            continue
        title, artist = (p.strip() for p in line.split("|", 1))
        tracks.append((title, artist))
    return tracks


def score_match(title: str, artist: str, item: dict) -> int:
    """Puntua un resultado de busqueda contra el titulo/artista buscados."""
    nt, na = normalize(title), normalize(artist)
    cand_title = normalize(item["name"])
    cand_artists = normalize(" ".join(a["name"] for a in item["artists"]))
    score = 0
    if nt and nt in cand_title:
        score += 3
    if cand_title == nt:
        score += 2
    # cualquiera de los artistas pedidos aparece en el candidato
    if any(tok and tok in cand_artists for tok in na.split()):
        score += 3
    score += int(item.get("popularity", 0) / 25)  # leve desempate por popularidad
    return score


def resolve_uri(sp: "spotipy.Spotify", title: str, artist: str) -> tuple[str | None, str]:
    """Devuelve (uri, etiqueta_legible). Primero usa hints; si no, busca."""
    hint = URI_HINTS_BY_TITLE.get(normalize(title))
    if hint:
        return hint, f"{title} — {artist} (hint)"

    # Busqueda amplia (mas tolerante que filtros track:/artist:)
    query = f"{title} {artist}"
    try:
        results = sp.search(q=query, type="track", limit=5).get("tracks", {}).get("items", [])
    except spotipy.SpotifyException as exc:
        return None, f"{title} — {artist} (error API: {exc})"
    if not results:
        return None, f"{title} — {artist} (SIN RESULTADOS)"

    best = max(results, key=lambda it: score_match(title, artist, it))
    got_artists = ", ".join(a["name"] for a in best["artists"])
    return best["uri"], f"{best['name']} — {got_artists}"


def chunked(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sube un tracklist exacto a Spotify.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo resuelve y muestra los matches; no crea nada.")
    parser.add_argument("--name", default=DEFAULT_PLAYLIST_NAME,
                        help=f"Nombre de la playlist (def: {DEFAULT_PLAYLIST_NAME}).")
    args = parser.parse_args()

    tracks = read_tracklist()
    print(f"Tracklist: {len(tracks)} canciones leidas de {TRACKLIST_FILE.name}\n")

    # Autenticacion PKCE (NO requiere client secret; abre el navegador la
    # primera vez y captura el callback en 127.0.0.1:8888 automaticamente).
    auth = SpotifyPKCE(scope=SCOPE, cache_path=str(HERE / ".cache"), open_browser=True)
    sp = spotipy.Spotify(auth_manager=auth)

    uris: list[str] = []
    missing: list[str] = []
    for i, (title, artist) in enumerate(tracks, 1):
        uri, label = resolve_uri(sp, title, artist)
        if uri:
            uris.append(uri)
            print(f"  {i:2d}. OK    {label}")
        else:
            missing.append(f"{title} — {artist}")
            print(f"  {i:2d}. FALTA {label}")

    print(f"\nResueltas {len(uris)}/{len(tracks)}.")
    if missing:
        print("No encontradas (revisa el nombre en tracklist.txt o agrega un hint):")
        for m in missing:
            print(f"   - {m}")

    if args.dry_run:
        print("\n--dry-run: no se creo nada. Quita la bandera para crear la playlist.")
        return
    if not uris:
        sys.exit("No hay nada que subir.")

    me = sp.current_user()
    playlist = sp.user_playlist_create(
        me["id"], args.name, public=False, description=PLAYLIST_DESCRIPTION
    )
    for batch in chunked(uris, 100):  # la API acepta max 100 por llamada
        sp.playlist_add_items(playlist["id"], batch)

    print(f"\n✓ Listo: '{args.name}' con {len(uris)} canciones en orden.")
    print(f"  {playlist['external_urls']['spotify']}")


if __name__ == "__main__":
    main()
