# Project Context: Notion <-> Frame.io V4 Sync

## Descripcion General

Cloud Function que sincroniza bidirecionalmente el status y metricas de assets entre una base de datos de Notion ("Tareas") y Frame.io V4. Desarrollado para el pipeline de produccion de **Globe Studio** dentro de **Efeonce Group**.

**Version actual:** 2.3.0
**Estado:** Produccion (deployed)

---

## Organizacion

- **Empresa:** Efeonce Group SpA
- **Unidad:** Globe Studio
- **Pipeline:** Post-produccion de contenido audiovisual
- **Repositorio:** https://github.com/cesargrowth11/notion-frame-io.git

---

## Arquitectura

```
                          +-------------------------+
  +------------+  POST    |                         |  PATCH    +------------+
  |            |--------->|   Cloud Function (GCP)  |---------->|            |
  |  Notion DB |          |   /notion-webhook       |           | Frame.io   |
  |  "Tareas"  |<---------|                         |<----------|  V4 API    |
  |            |  UPDATE   |   /frameio-webhook      |  GET      |            |
  +------------+  counts  +-------------------------+  counts   +------------+
```

### Flujos de datos

| Flujo | Trigger | Accion |
|-------|---------|--------|
| 1. Notion -> Frame.io | Status cambia en Notion | Webhook POST a `/notion-webhook`, actualiza status en Frame.io via metadata values API |
| 2. Frame.io -> Notion | Nueva version o comentario en Frame.io | Webhook POST a `/frameio-webhook`, actualiza conteos en Notion |
| 3. Pull on status change | Status cambia en Notion | Ademas de Flujo 1, trae conteos de Frame.io de vuelta a Notion |

---

## Infraestructura

| Componente | Valor |
|------------|-------|
| Plataforma | Google Cloud Functions (2nd Gen) |
| Runtime | Python 3.12 |
| Region | us-central1 |
| Proyecto GCP | efeonce-group |
| Memoria | 256 MB |
| Timeout | 60s |
| Instancias | 0-10 (auto-scale) |
| URL publica | `https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync` |
| Entry point | `sync_status` |

---

## Estructura de archivos

```
notion-frame-io/
+-- main.py                      # Cloud Function principal (toda la logica)
+-- requirements.txt             # Dependencias Python
+-- .env.yaml                    # Variables de entorno (SECRETO, gitignored)
+-- deploy.sh                    # Script de deploy a GCP
+-- generate_frameio_token.py    # Helper: generar OAuth token de Frame.io V4
+-- get_frameio_status_uuids.py  # Helper: descubrir UUIDs de metadata fields
+-- .gitignore                   # Excluye secrets y archivos temporales
+-- .gcloudignore                # Generado por gcloud deploy
+-- README.md                    # Documentacion de uso
+-- CHANGELOG.md                 # Historial de cambios (ver detalle)
+-- project_context.md           # Este archivo
```

---

## Dependencias (requirements.txt)

| Paquete | Version | Uso |
|---------|---------|-----|
| functions-framework | 3.* | Framework de Google Cloud Functions |
| flask | >=2.0 | HTTP request/response (viene con functions-framework) |
| requests | >=2.28 | Llamadas HTTP a Frame.io y Notion APIs |
| google-cloud-functions | >=1.0 | Persistir tokens en env vars de la Cloud Function |

---

## APIs y Servicios Externos

### Frame.io V4 API
- **Base URL:** `https://api.frame.io`
- **Autenticacion:** OAuth 2.0 Bearer token (Adobe IMS)
- **Endpoints usados:**
  - `PATCH /v4/accounts/{id}/projects/{id}/metadata/values` — Actualizar status de asset
  - `GET /v2/assets/{id}` — Obtener info de asset (comment_count, type, parent_id)
  - `GET /v2/assets/{id}/children` — Listar children de un asset (version stacks, folders)
  - `GET /v2/projects/{id}` — Obtener info del proyecto (root_asset_id)

### Adobe IMS (Token Refresh)
- **URL:** `https://ims-na1.adobelogin.com/ims/token/v3`
- **Flujo:** `grant_type=refresh_token` con client_id + client_secret
- **Auto-refresh:** Cuando Frame.io responde 401, se intenta refresh automaticamente

### Notion API
- **Base URL:** `https://api.notion.com/v1`
- **Version:** 2022-06-28
- **Endpoints usados:**
  - `POST /databases/{id}/query` — Buscar pagina por URL de Frame.io
  - `PATCH /pages/{id}` — Actualizar propiedades (conteos)

---

## Base de Datos Notion: "Tareas"

**Database ID:** `3a54f0904be14158833533ba96557a73`

### Propiedades relevantes

| Propiedad | Tipo | Descripcion |
|-----------|------|-------------|
| Estado | Status | Trigger del sync (mapea a status de Frame.io) |
| URL Frame.io | URL | URL del asset en Frame.io (pegada manualmente) |
| Frame Versions | Number | Cantidad de versiones en el version stack (automatico) |
| Frame Comments | Number | Cantidad de comentarios del asset (automatico) |

---

## Mapeo de Status

| Notion (Estado) | Frame.io | Variable de entorno |
|-----------------|----------|---------------------|
| En curso | In Progress | `FRAMEIO_STATUS_IN_PROGRESS` |
| Listo para revision | Needs Review | `FRAMEIO_STATUS_NEEDS_REVIEW` |
| Cambios Solicitados | Changes Requested | `FRAMEIO_STATUS_CHANGES_REQUESTED` |
| Listo | Approved / Final | `FRAMEIO_STATUS_APPROVED` |

Cada status de Frame.io se identifica por un UUID configurado en `.env.yaml`.
El matching de status normaliza acentos, mayusculas/minusculas y espacios antes de resolver el UUID de Frame.io.

---

## Variables de Entorno

### Notion
| Variable | Descripcion |
|----------|-------------|
| `NOTION_TOKEN` | Token de integracion de Notion |
| `NOTION_DATABASE_ID` | ID de la base de datos "Tareas" |
| `NOTION_PROP_STATUS` | Nombre de la propiedad de status (default: "Estado") |
| `NOTION_PROP_FRAME_URL` | Nombre de la propiedad de URL (default: "URL Frame.io") |
| `NOTION_PROP_VERSIONS` | Nombre de la propiedad de versiones (default: "Frame Versions") |
| `NOTION_PROP_COMMENTS` | Nombre de la propiedad de comentarios (default: "Frame Comments") |

### Frame.io
| Variable | Descripcion |
|----------|-------------|
| `FRAMEIO_ACCESS_TOKEN` | OAuth access token (se auto-renueva) |
| `FRAMEIO_REFRESH_TOKEN` | OAuth refresh token (se actualiza junto al access token) |
| `FRAMEIO_CLIENT_ID` | Client ID de la app Adobe/Frame.io |
| `FRAMEIO_CLIENT_SECRET` | Client Secret de la app Adobe/Frame.io |
| `FRAMEIO_ACCOUNT_ID` | Account ID de Frame.io |
| `FRAMEIO_PROJECT_ID` | Project ID de Frame.io |
| `FRAMEIO_STATUS_FIELD_ID` | UUID del campo de metadata "Status" |
| `FRAMEIO_STATUS_IN_PROGRESS` | UUID del valor "In Progress" |
| `FRAMEIO_STATUS_NEEDS_REVIEW` | UUID del valor "Needs Review" |
| `FRAMEIO_STATUS_CHANGES_REQUESTED` | UUID del valor "Changes Requested" |
| `FRAMEIO_STATUS_APPROVED` | UUID del valor "Approved" |

---

## Endpoints

| Metodo | Path | Descripcion |
|--------|------|-------------|
| GET | `/` | Health check: version, estado del mapping, DB ID |
| POST | `/notion-webhook` | Recibe webhook de Notion, sincroniza status y conteos |
| POST | `/frameio-webhook` | Recibe webhook de Frame.io, actualiza conteos en Notion |

---

## Funcionalidades Clave del Codigo (main.py)

### URL Parser (parse_asset_id)
Extrae el asset ID de Frame.io de cualquier formato de URL:
- URLs estandar: `frame.io/player/{uuid}`, `frame.io/reviews/.../{uuid}`, `frame.io/projects/.../files/{uuid}`
- URLs acortadas: `f.io/xxx`, `fio.co/xxx` — resuelve via HTTP HEAD redirect
- URLs de vista: `next.frame.io/.../view/...` — busca asset en el arbol del proyecto
- Fallback: busqueda recursiva en children del proyecto comparando `view_url`
- Si la URL es `next.frame.io/project/.../view/{uuid}`, el asset ID se extrae directamente via regex
- Si la URL de vista no trae el asset ID de forma directa, se usa busqueda por proyecto como fallback
- UUID directo: acepta un UUID sin URL

### Parser de Webhook de Notion
- `parse_notion_payload()` intenta leer propiedades tanto desde `data` como desde `data.properties`
- Si el webhook no incluye URL o status, `notion_get_page()` consulta la pagina completa en Notion usando `page_id`
- Esto hace el flujo mas tolerante a payloads minimos enviados por Notion Automations

### Token Auto-Refresh
- Todas las llamadas a Frame.io pasan por `_fio_request()`
- Si la API responde 401, se intenta refresh via Adobe IMS
- Los nuevos tokens se persisten en las env vars de la Cloud Function via GCP API
- Si la persistencia falla, los tokens se mantienen en memoria hasta el proximo cold start

### Conteo Inteligente de Versiones
- Detecta si el asset es un version stack o esta dentro de uno
- Cuenta children del version stack para obtener total de versiones
- Suma `comment_count` de todas las versiones para un total correcto

---

## Deploy

### Comando rapido
```bash
./deploy.sh
```

### Comando manual (Windows con gcloud)
```bash
gcloud functions deploy notion-frameio-sync \
  --gen2 --region=us-central1 --runtime=python312 \
  --source=. --entry-point=sync_status \
  --trigger-http --allow-unauthenticated \
  --env-vars-file=.env.yaml \
  --memory=256MB --timeout=60s \
  --min-instances=0 --max-instances=10 \
  --project=efeonce-group
```

### Verificar deploy
```bash
curl https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync
```

Respuesta esperada:
```json
{
  "service": "notion-frameio-sync",
  "version": "2.3.0",
  "status": "ok",
  "endpoints": ["/notion-webhook", "/frameio-webhook"],
  "mapping": {
    "En curso": "ok",
    "Listo para revision": "ok",
    "Cambios Solicitados": "ok",
    "Listo": "ok"
  }
}
```

---

## Historial de Cambios

Ver [CHANGELOG.md](CHANGELOG.md) para el detalle completo de cambios por version.

---

## Consideraciones

- **Token expiration:** Los access tokens de Frame.io V4 expiran cada ~1 hora. El auto-refresh maneja esto transparentemente.
- **Refresh token expiration:** Los refresh tokens de Adobe IMS expiran en ~14 dias. Si expira, hay que regenerar manualmente con `generate_frameio_token.py`.
- **Rate limits:** Frame.io tiene rate limiting progresivo. Con el volumen tipico de Globe Studio no deberia ser problema.
- **Cold starts:** En cold start la Cloud Function lee los tokens de las env vars. Si el auto-refresh persiste correctamente, los tokens sobreviven cold starts.
- **Notion automation 200:** La funcion siempre responde 200 cuando no hay URL de Frame.io, para evitar que Notion pause la automatizacion por errores.
- **Busqueda de assets:** La busqueda por proyecto (fallback) recorre hasta 2 niveles de profundidad con page_size=50 por nivel. Proyectos muy grandes podrian necesitar mas profundidad o paginacion.
