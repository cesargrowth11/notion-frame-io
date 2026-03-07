# Project Context: Notion <-> Frame.io V4 Sync

## Descripcion General

Cloud Function que sincroniza status y senales de revision entre la base `Tareas` de Notion y un proyecto de Frame.io V4.

**Version actual:** 2.3.1  
**Estado:** Produccion (deployed)

## Organizacion

- Empresa: Efeonce Group SpA
- Unidad: Globe Studio
- Pipeline: Post-produccion de contenido audiovisual
- Repositorio: https://github.com/cesargrowth11/notion-frame-io.git

## Arquitectura

```text
Notion Automation -> /notion-webhook -> Frame.io status update + pull de senales
Frame.io Webhook  -> /frameio-webhook -> Notion property updates
```

### Flujos de datos

| Flujo | Trigger | Accion |
|-------|---------|--------|
| 1. Notion -> Frame.io | Cambio de `Estado` en Notion | Actualiza `Status` del asset en Frame.io |
| 2. Frame.io -> Notion | `file.*` o `comment.*` | Actualiza conteos y senales de revision en Notion |
| 3. Pull on status change | `/notion-webhook` | Refresca conteos y senales de Frame.io para la tarea |

## Infraestructura

| Componente | Valor |
|------------|-------|
| Plataforma | Google Cloud Functions (2nd Gen) |
| Runtime | Python 3.12 |
| Region | us-central1 |
| Proyecto GCP | efeonce-group |
| Memoria | 256 MB |
| Timeout | 60s |
| Instancias | 0-10 |
| URL publica | `https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync` |
| Entry point | `sync_status` |

## Archivos principales

```text
notion-frame-io/
+-- main.py
+-- requirements.txt
+-- .env.yaml
+-- deploy.sh
+-- generate_frameio_token.py
+-- get_frameio_status_uuids.py
+-- README.md
+-- CHANGELOG.md
+-- BUGS.md
+-- TASKS.md
+-- HANDOFF.md
+-- project_context.md
```

## Dependencias

| Paquete | Version | Uso |
|---------|---------|-----|
| functions-framework | 3.* | Runtime HTTP de Cloud Functions |
| flask | >=2.0 | `jsonify` y capa HTTP |
| requests | >=2.28 | Llamadas HTTP a Notion y Frame.io |
| google-cloud-secret-manager | >=2.0 | Lectura/escritura de tokens OAuth |

## APIs y Servicios Externos

### Frame.io API

- Base URL: `https://api.frame.io`
- Auth: OAuth 2.0 Bearer token via Adobe IMS
- Endpoints usados:
  - `PATCH /v4/accounts/{account_id}/projects/{project_id}/metadata/values`
  - `GET /v4/accounts/{account_id}/files/{file_id}/metadata`
  - `GET /v4/accounts/{account_id}/files/{file_id}/comments`
  - `GET /v4/accounts/{account_id}/comments/{comment_id}`
  - `GET /v2/assets/{asset_id}`
  - `GET /v2/assets/{asset_id}/children`
  - `GET /v2/projects/{project_id}`

### Adobe IMS

- URL: `https://ims-na1.adobelogin.com/ims/token/v3`
- Uso: refresh automatico cuando Frame.io responde `401`

### Google Cloud Secret Manager

- Secrets default:
  - `frameio-access-token`
  - `frameio-refresh-token`
- Uso:
  - leer tokens al cold start
  - persistir nuevas versiones tras refresh
- IAM necesario en la service account:
  - `roles/secretmanager.secretAccessor`
  - `roles/secretmanager.secretVersionManager`

### Notion API

- Base URL: `https://api.notion.com/v1`
- Version: `2022-06-28`
- Endpoints usados:
  - `POST /databases/{id}/query`
  - `GET /pages/{id}`
  - `PATCH /pages/{id}`

## Base de Datos Notion: `Tareas`

**Database ID:** `3a54f0904be14158833533ba96557a73`

### Propiedades relevantes

| Propiedad | Tipo | Rol |
|-----------|------|-----|
| `Estado` | Status | Trigger desde Notion |
| `URL Frame.io` | URL | URL manual del asset |
| `Frame Asset ID` | Rich text | Clave primaria de asociacion |
| `Frame Versions` | Number | Total de versiones |
| `Frame Comments` | Number | Total de comentarios |
| `Open Frame Comments` | Number | Comentarios abiertos |
| `Resolved Frame Comments` | Number | Comentarios resueltos |
| `Last Frame Comment` | Rich text | Texto del ultimo comentario |
| `Last Frame Comment ID` | Rich text | ID del ultimo comentario |
| `Last Frame Comment At` | Date | Fecha del ultimo comentario |
| `Last Frame Comment Timecode` | Rich text | Timecode del ultimo comentario |
| `Last Reviewed Version` | Number | Version base de la ronda |
| `Client Review Open` | Checkbox | Ronda de cliente abierta |
| `Client Change Round` | Number | Contador persistente de rondas |
| `RpA` | Formula | Calculado en Notion |
| `Semaforo RpA` | Formula | Calculado en Notion |

### Estrategia de asociacion

- Primero se busca por `Frame Asset ID`
- Si no existe, fallback a `URL Frame.io`
- Cuando la funcion identifica una pagina, persiste `Frame Asset ID`

## Mapeo de status

| Notion | Frame.io | Variable |
|--------|----------|----------|
| `En curso` | `In Progress` | `FRAMEIO_STATUS_IN_PROGRESS` |
| `Listo para revision` | `Needs Review` | `FRAMEIO_STATUS_NEEDS_REVIEW` |
| `Cambios Solicitados` | `Changes requested` | `FRAMEIO_STATUS_CHANGES_REQUESTED` |
| `Listo` | `Approved` | `FRAMEIO_STATUS_APPROVED` |

### Estado real del mapping

- `En curso` esta validado en produccion
- `Cambios Solicitados` no es confiable todavia
- Ver `BUG-006`

## Modelo actual de RpA

- La Cloud Function **no** calcula `RpA`
- La Cloud Function **no** calcula `Semaforo RpA`
- Ambas propiedades deben seguir como formulas de Notion

### Senales que hoy alimentan ese modelo

- `Frame Versions`
- `Frame Comments`
- `Open Frame Comments`
- `Resolved Frame Comments`
- `Last Frame Comment`
- `Last Frame Comment At`
- `Last Frame Comment Timecode`
- `Last Reviewed Version`
- `Client Review Open`
- `Client Change Round`

### Logica actual de `Client Change Round`

- abre ronda con `comment.created`
- cierra ronda con `file.versioned`
- no usa `Cambios Solicitados` como disparador principal mientras `BUG-006` siga abierto

### Plan pendiente: comentarios automáticos en Notion

- La API de Notion permite crear comentarios en paginas/bloques.
- Idea propuesta:
  - seguir usando propiedades como fuente estructurada para `RpA` y `Semaforo RpA`
  - opcionalmente publicar tambien un comentario en la pagina de Notion cuando llegue feedback desde Frame.io
- Objetivo:
  - dejar una bitacora legible en la tarea sin mezclar esa bitacora con el calculo estructurado

## Variables de entorno

### Notion

- `NOTION_TOKEN`
- `NOTION_DATABASE_ID`
- `NOTION_PROP_STATUS`
- `NOTION_PROP_FRAME_URL`
- `NOTION_PROP_ASSET_ID`
- `NOTION_PROP_VERSIONS`
- `NOTION_PROP_COMMENTS`
- `NOTION_PROP_OPEN_COMMENTS`
- `NOTION_PROP_RESOLVED_COMMENTS`
- `NOTION_PROP_LAST_COMMENT`
- `NOTION_PROP_LAST_COMMENT_ID`
- `NOTION_PROP_LAST_COMMENT_AT`
- `NOTION_PROP_LAST_COMMENT_TIMECODE`
- `NOTION_PROP_LAST_REVIEWED_VERSION`
- `NOTION_PROP_CLIENT_REVIEW_OPEN`
- `NOTION_PROP_CHANGE_ROUND`

### Frame.io

- `FRAMEIO_ACCESS_TOKEN`
- `FRAMEIO_REFRESH_TOKEN`
- `FRAMEIO_CLIENT_ID`
- `FRAMEIO_CLIENT_SECRET`
- `FRAMEIO_ACCOUNT_ID`
- `FRAMEIO_PROJECT_ID`
- `FRAMEIO_STATUS_FIELD_ID`
- `FRAMEIO_STATUS_IN_PROGRESS`
- `FRAMEIO_STATUS_NEEDS_REVIEW`
- `FRAMEIO_STATUS_CHANGES_REQUESTED`
- `FRAMEIO_STATUS_APPROVED`
- `SM_ACCESS_SECRET`
- `SM_REFRESH_SECRET`

## Endpoints

| Metodo | Path | Descripcion |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/notion-webhook` | Notion -> Frame.io + refresh de senales |
| `POST` | `/frameio-webhook` | Frame.io -> Notion |

## Webhook de Frame.io

- Workspace: `c90b7046-2ad9-4097-bcb4-3a81ee239398`
- URL: `https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync/frameio-webhook`
- Eventos activos confirmados:
  - `file.created`
  - `file.versioned`
  - `comment.created`
  - `comment.deleted`

### Follow-up abierto

- ampliar a `comment.completed`
- ampliar a `comment.uncompleted`

## Funcionalidades clave del codigo

### URL y asset resolution

- `parse_asset_id()` soporta UUID directo, URLs tradicionales, `f.io`, `fio.co` y `next.frame.io`
- fallback de busqueda por proyecto para URLs no triviales

### Notion payload parsing

- `parse_notion_payload()` lee desde `data` y `data.properties`
- usa `Frame Asset ID` antes que la URL
- si faltan propiedades, usa `notion_get_page(page_id)`

### Token refresh

- `_fio_request()` reintenta con refresh si recibe `401`
- los tokens nuevos se guardan en Secret Manager

### Conteo y senales

- `fio_get_counts()` usa metadata V4 para `Comment Count`
- V2 se usa para la logica de versiones/version stacks
- `fio_get_comment_signals()` extrae ultimo comentario y abiertos/resueltos
- `notion_calculate_review_state()` mantiene `Client Change Round`

## Deploy

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

## Consideraciones

- access tokens expiran rapido; el sistema usa refresh automatico
- open/resolved comments hoy se mantienen bien con `comment.created`, `comment.deleted` y `file.versioned`
- `Last Frame Comment By` aun no existe porque el payload real disponible no trae actor enriquecido en la ruta que estamos usando
- el endpoint de webhook de Frame.io sigue sin verificacion de firma

## Documentacion complementaria

- Ver `CHANGELOG.md`
- Ver `BUGS.md`
- Ver `TASKS.md`
- Ver `HANDOFF.md`
