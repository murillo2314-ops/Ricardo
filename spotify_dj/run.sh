#!/usr/bin/env bash
# Lanzador de un comando: instala, verifica y crea la playlist "Trippy Trip".
# Uso:  bash run.sh
set -euo pipefail
cd "$(dirname "$0")"

# Credenciales (ya con tu Client ID; PKCE, sin secret). Se pueden sobrescribir
# exportando estas variables antes de correr.
export SPOTIPY_CLIENT_ID="${SPOTIPY_CLIENT_ID:-148e68bebbd64d9aa14409831b26c972}"
export SPOTIPY_REDIRECT_URI="${SPOTIPY_REDIRECT_URI:-http://127.0.0.1:8888/callback}"

echo "==> Instalando dependencias..."
python3 -m pip install -q -r requirements.txt

echo "==> Verificando el tracklist (dry-run, no crea nada todavia)..."
python3 build_playlist.py --dry-run

echo
read -r -p "¿Crear la playlist en tu Spotify ahora? [y/N] " ok
if [[ "${ok:-}" == "y" || "${ok:-}" == "Y" ]]; then
  python3 build_playlist.py
else
  echo "Cancelado. Cuando quieras: python3 build_playlist.py"
fi
