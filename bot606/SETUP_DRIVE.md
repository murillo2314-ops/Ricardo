# Configurar Google Drive en el Bot 606

El bot puede subir y actualizar automáticamente el Excel `606_YYYY-MM.xlsx` en
una carpeta de tu Google Drive después de cada factura. Esto es **opcional**: si
no lo configuras, el bot funciona igual y descargas el Excel con `/exportar`.

## Paso 1 — Crear la cuenta de servicio (una sola vez)

1. Entra a <https://console.cloud.google.com/> e inicia sesión con tu cuenta de Google.
2. Crea un proyecto nuevo (arriba a la izquierda → "Nuevo proyecto"), nómbralo p.ej. `bot-606`.
3. Activa la API de Drive: busca **"Google Drive API"** → **Habilitar**.
4. Ve a **APIs y servicios → Credenciales → Crear credenciales → Cuenta de servicio**.
   - Nombre: `bot-606-drive`. Continúa y crea.
5. Abre la cuenta de servicio recién creada → pestaña **Claves** → **Agregar clave → Crear clave nueva → JSON**.
   - Se descarga un archivo `.json`. **Ese es el contenido de `GOOGLE_SERVICE_ACCOUNT_JSON`.**
6. Copia el **email** de la cuenta de servicio (algo como
   `bot-606-drive@bot-606.iam.gserviceaccount.com`). Lo necesitas en el paso 2.

## Paso 2 — Compartir la carpeta de Drive

1. En Google Drive crea una carpeta, p.ej. **`606 Facturas`**.
2. Clic derecho → **Compartir** → pega el **email de la cuenta de servicio** →
   permiso **Editor** → Enviar.
3. Abre la carpeta y copia su **ID** desde la URL:
   ```
   https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUvWxYz
                                            └──────────── este es el ID ────┘
   ```
   Ese es el valor de `GDRIVE_FOLDER_ID`.

## Paso 3 — Variables en Railway

En tu servicio de Railway → pestaña **Variables**, agrega:

| Variable | Valor |
|----------|-------|
| `TELEGRAM_BOT_TOKEN` | (ya la tienes) |
| `ANTHROPIC_API_KEY` | Tu clave de Claude (`sk-ant-...`) — la "VARIABLE 2" |
| `ALLOWED_USERS` | Tu user ID de Telegram (de @userinfobot) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Pega **todo** el contenido del `.json` descargado |
| `GDRIVE_FOLDER_ID` | El ID de la carpeta del paso 2 |
| `DB_PATH` | `/data/facturas.db` (ver Paso 4) |

> El JSON es largo y multilínea — Railway acepta pegarlo completo en el campo de valor.

## Paso 4 — Volumen persistente (importante)

Railway borra los archivos en cada despliegue. Para no perder la base de datos:

1. En el servicio → **Settings → Volumes → New Volume**.
2. Mount path: `/data`.
3. Asegúrate de que `DB_PATH=/data/facturas.db` (paso 3).

Así las facturas sobreviven a los reinicios. El Excel, además, queda respaldado en Drive.

## Listo

Cuando aceptes una factura en el bot, verás un mensaje
**"☁️ Excel actualizado en Drive"** con el enlace. El mismo archivo
`606_YYYY-MM.xlsx` se reemplaza cada vez (no se crean copias), así siempre
tienes la versión más reciente en la carpeta compartida.
