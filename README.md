# Notion <-> Frame.io V4 Sync

Cloud Function para sincronizar estados y señales de revision entre la base `Tareas` de Notion y un proyecto de Frame.io.

## Estado actual

- `Notion -> Frame.io`: funcional para `En curso`
- `Frame.io -> Notion`: funcional para versiones, comentarios y senales base de revision
- `Client Change Round`: funcional en primer corte
- `Cambios Solicitados -> Changes requested`: no confiable todavia, ver `BUG-006`

## Que hace hoy

### 1. Notion -> Frame.io

Cuando cambia `Estado` en Notion, la funcion intenta actualizar el campo `Status` del asset en Frame.io.

### 2. Frame.io -> Notion

Cuando llega un webhook de Frame.io:

- actualiza `Frame Versions`
- actualiza `Frame Comments`
- actualiza `Open Frame Comments`
- actualiza `Resolved Frame Comments`
- actualiza `Last Frame Comment`
- actualiza `Last Frame Comment ID`
- actualiza `Last Frame Comment At`
- actualiza `Last Frame Comment Timecode`
- actualiza `Last Reviewed Version`
- actualiza `Client Review Open`
- actualiza `Client Change Round`

### 3. Pull on status change

Cuando Notion llama `/notion-webhook`, la funcion tambien refresca las senales de Frame.io para esa tarea.

## Modelo actual de RpA

La Cloud Function no calcula `RpA` ni `Semaforo RpA`.

La funcion solo escribe senales base en Notion. Las formulas de `RpA` y `Semaforo RpA` deben vivir en Notion.

### Senales disponibles en Notion

| Propiedad | Tipo | Uso |
|-----------|------|-----|
| `Frame Asset ID` | Rich text | Clave explicita de asociacion con el asset |
| `Frame Versions` | Number | Total de versiones del asset/version stack |
| `Frame Comments` | Number | Total de comentarios |
| `Open Frame Comments` | Number | Comentarios abiertos |
| `Resolved Frame Comments` | Number | Comentarios resueltos |
| `Last Frame Comment` | Rich text | Ultimo comentario visible |
| `Last Frame Comment ID` | Rich text | ID del ultimo comentario |
| `Last Frame Comment At` | Date | Fecha del ultimo comentario |
| `Last Frame Comment Timecode` | Rich text | Timecode formateado del ultimo comentario |
| `Last Reviewed Version` | Number | Version base de la ronda actual |
| `Client Review Open` | Checkbox | Indica si la ronda sigue abierta |
| `Client Change Round` | Number | Contador persistente de rondas |

### Logica actual de `Client Change Round`

- abre una ronda con `comment.created`
- cierra la ronda con `file.versioned`
- no usa `Cambios Solicitados` como senal principal mientras `BUG-006` siga abierto

## Arquitectura

```text
Notion Automation -> /notion-webhook -> Frame.io status update + pull de senales
Frame.io Webhook  -> /frameio-webhook -> Notion property updates
```

## Requisitos

- Google Cloud Functions Gen 2
- Python 3.12
- proyecto GCP `efeonce-group`
- acceso a Notion API
- acceso a Frame.io API
- Secret Manager para tokens OAuth

## Variables importantes

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

## Endpoints

| Metodo | Path | Uso |
|--------|------|-----|
| `GET` | `/` | health check |
| `POST` | `/notion-webhook` | status sync y pull de senales |
| `POST` | `/frameio-webhook` | push de senales desde Frame.io |

## Webhook activo de Frame.io

- Workspace: `c90b7046-2ad9-4097-bcb4-3a81ee239398`
- URL: `https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync/frameio-webhook`
- Eventos activos confirmados:
  - `file.created`
  - `file.versioned`
  - `comment.created`
  - `comment.deleted`

## Limitaciones conocidas

- `BUG-006`: `Cambios Solicitados` no esta validado como sync confiable hacia `Changes requested`
- el webhook actual no quedo ampliado de forma confirmada a `comment.completed` / `comment.uncompleted`
- el payload real de comentarios no trae autor de forma rica, por eso no existe aun `Last Frame Comment By`

## Documentacion operativa

- Ver [CHANGELOG.md](CHANGELOG.md) para cambios por version
- Ver [BUGS.md](BUGS.md) para causas raiz y resoluciones
- Ver [TASKS.md](TASKS.md) para pendientes activos
- Ver [HANDOFF.md](HANDOFF.md) para traspasos operativos
- Ver [project_context.md](project_context.md) para contexto del proyecto
