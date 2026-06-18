# 🎛️ Trippy Trip — builder de playlist exacta

Sube un tracklist **exacto y ordenado** a una playlist tuya de Spotify usando la
Web API oficial. Esto **sí** inserta las canciones específicas que quieres (a
diferencia del generador "por vibe", que solo aproxima el estilo).

## Qué hace

1. Lee `tracklist.txt` (una canción por línea: `Título | Artista`).
2. Resuelve cada canción a su ID de Spotify (usa IDs ya confirmados cuando los
   tiene; si no, busca en Spotify y elige el mejor match).
3. Crea una playlist privada **Trippy Trip** y añade todo **en orden**.

## Setup (una sola vez, ~2 min)

### 1. Crea una Spotify Developer App
- Entra a <https://developer.spotify.com/dashboard> e inicia sesión.
- **Create app**. Nombre/desc: lo que quieras.
- En **Redirect URIs** agrega EXACTAMENTE:
  ```
  http://127.0.0.1:8888/callback
  ```
- Guarda. Copia el **Client ID** y el **Client Secret**.

### 2. Exporta tus credenciales
```bash
export SPOTIPY_CLIENT_ID=tu_client_id
export SPOTIPY_CLIENT_SECRET=tu_client_secret
export SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
```
> No subas estas credenciales al repo. El token queda en `.cache` (ya está en
> `.gitignore`).

### 3. Instala dependencias
```bash
pip install -r requirements.txt
```

## Uso

```bash
# 1) Verifica que encuentra cada canción (no crea nada todavía):
python build_playlist.py --dry-run

# 2) Si los matches se ven bien, créala de verdad:
python build_playlist.py
```

La primera vez se abrirá el navegador para que autorices la app con tu cuenta.
Al terminar imprime el link de la playlist.

### Opciones
- `--name "Otro nombre"` → cambia el nombre de la playlist.
- `PLAYLIST_NAME=... ` como variable de entorno hace lo mismo.

## Editar el set

Abre `tracklist.txt` y agrega/quita/reordena líneas (`Título | Artista`). El
orden del archivo es el orden en la playlist. Si una canción no la encuentra,
revisa el nombre exacto o añade su ID en `URI_HINTS_BY_TITLE` dentro de
`build_playlist.py`.

## Seguridad
- `.cache` y `.env` están en `.gitignore` — no se suben.
- La app solo pide los permisos `playlist-modify-private` y
  `playlist-modify-public`. No lee ni modifica nada más.
