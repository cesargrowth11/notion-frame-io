# Notion <-> Frame.io V4 Sync

Cloud Function para sincronizar estados y senales de revision entre una base de datos de Notion y un proyecto de Frame.io V4.

## Que hace

### 1. Notion -> Frame.io

Cuando cambia el estado de una tarea en Notion, la funcion actualiza el campo `Status` del asset correspondiente en Frame.io.

### 2. Frame.io -> Notion

Cuando llega un evento de Frame.io (`file.created`, `file.versioned`, `comment.created`, `comment.deleted`), la funcion actualiza propiedades de la tarea en Notion:

- conteos de versiones y comentarios
- senales de revision (abiertos, resueltos, ultima actividad)
- contador de rondas de cambio por version (`Client Change Round`)
- opcionalmente, espeja el comentario como un page comment en Notion

### 3. Pull on status change

Al procesar un cambio de estado desde Notion, la funcion tambien refresca las senales de Frame.io para esa tarea.

### Workflow-backed rounds

Para piezas que no pasan por Frame.io (PDFs, brochures, landing pages), la funcion cuenta rondas de revision desde transiciones de estado en Notion, sin depender de Frame.io.

## Arquitectura

```text
Notion Automation -> /notion-webhook -> Frame.io status update + pull de senales
Frame.io Webhook  -> /frameio-webhook -> Notion property updates
```

## Requisitos

- Google Cloud Functions Gen 2
- Python 3.12
- Acceso a Notion API
- Acceso a Frame.io API (OAuth V4)
- Google Cloud Secret Manager para tokens OAuth

## Setup

### 1. Crear archivo de variables de entorno

Copiar `.env.yaml.example` a `.env.yaml` y completar los valores:

```yaml
# Notion
NOTION_TOKEN: "<tu-notion-integration-token>"
NOTION_DATABASE_ID: "<id-de-tu-base-de-datos>"
NOTION_PROP_STATUS: "Estado"
NOTION_PROP_FRAME_URL: "URL Frame.io"
NOTION_PROP_ASSET_ID: "Frame Asset ID"
NOTION_PROP_VERSIONS: "Frame Versions"
NOTION_PROP_COMMENTS: "Frame Comments"
NOTION_PROP_OPEN_COMMENTS: "Open Frame Comments"
NOTION_PROP_RESOLVED_COMMENTS: "Resolved Frame Comments"
NOTION_PROP_LAST_COMMENT: "Last Frame Comment"
NOTION_PROP_LAST_COMMENT_ID: "Last Frame Comment ID"
NOTION_PROP_LAST_COMMENT_AT: "Last Frame Comment At"
NOTION_PROP_LAST_COMMENT_TIMECODE: "Last Frame Comment Timecode"
NOTION_PROP_LAST_REVIEWED_VERSION: "Last Reviewed Version"
NOTION_PROP_CLIENT_REVIEW_OPEN: "Client Review Open"
NOTION_PROP_CHANGE_ROUND: "Client Change Round"
NOTION_ENABLE_FRAME_COMMENT_MIRROR: "true"

# Frame.io
FRAMEIO_ACCESS_TOKEN: "<token-inicial>"
FRAMEIO_REFRESH_TOKEN: "<refresh-token>"
FRAMEIO_CLIENT_ID: "<client-id>"
FRAMEIO_CLIENT_SECRET: "<client-secret>"
FRAMEIO_ACCOUNT_ID: "<account-id>"
FRAMEIO_PROJECT_ID: "<project-id>"
FRAMEIO_STATUS_FIELD_ID: "<metadata-field-id>"
FRAMEIO_STATUS_IN_PROGRESS: "<uuid-status>"
FRAMEIO_STATUS_NEEDS_REVIEW: "<uuid-status>"
FRAMEIO_STATUS_CHANGES_REQUESTED: "<uuid-status>"
FRAMEIO_STATUS_APPROVED: "<uuid-status>"

# Secret Manager
SM_ACCESS_SECRET: "frameio-access-token"
SM_REFRESH_SECRET: "frameio-refresh-token"
```

### 2. Configurar Secret Manager

Crear los secrets en GCP y otorgar permisos a la service account:

```bash
gcloud secrets create frameio-access-token --project=<tu-proyecto>
gcloud secrets create frameio-refresh-token --project=<tu-proyecto>

# IAM para la service account de la Cloud Function
gcloud secrets add-iam-policy-binding frameio-access-token \
  --member="serviceAccount:<tu-sa>@<tu-proyecto>.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretVersionManager" \
  --project=<tu-proyecto>
```

### 3. Deploy

```bash
gcloud functions deploy <nombre-funcion> \
  --gen2 --region=<region> --runtime=python312 \
  --source=. --entry-point=sync_status \
  --trigger-http --allow-unauthenticated \
  --env-vars-file=.env.yaml \
  --memory=256MB --timeout=60s \
  --min-instances=0 --max-instances=10 \
  --project=<tu-proyecto>
```

### 4. Configurar webhooks

**Notion:** crear una automation en la base de datos que envie un POST a `/notion-webhook` cuando cambie el estado de una tarea.

**Frame.io:** crear un workspace webhook apuntando a `/frameio-webhook` con los eventos `file.created`, `file.versioned`, `comment.created`, `comment.deleted`.

## Endpoints

| Metodo | Path | Uso |
|--------|------|-----|
| `GET` | `/` | Health check |
| `POST` | `/notion-webhook` | Status sync y pull de senales |
| `POST` | `/frameio-webhook` | Push de senales desde Frame.io |

## Propiedades de Notion

| Propiedad | Tipo | Descripcion |
|-----------|------|-------------|
| `Frame Asset ID` | Rich text | Clave de asociacion con el asset |
| `Frame Versions` | Number | Total de versiones |
| `Frame Comments` | Number | Total de comentarios |
| `Open Frame Comments` | Number | Comentarios abiertos |
| `Resolved Frame Comments` | Number | Comentarios resueltos |
| `Last Frame Comment` | Rich text | Texto del ultimo comentario |
| `Last Frame Comment Version` | Number | Version del ultimo comentario |
| `Last Reviewed Version` | Number | Ultima version con ronda abierta |
| `Client Review Open` | Checkbox | Ronda de revision abierta |
| `Client Change Round` | Number | Contador de rondas por version |
| `Workflow Change Round` | Number | Rondas para tareas sin Frame.io |
| `Review Source` | Select | `Frame.io`, `Workflow`, o `Auto` |

## Logica de rondas

### Tareas con Frame.io
- primer `comment.created` en una version nueva abre una ronda
- `file.versioned` cierra la ronda
- comentarios adicionales en la misma version no incrementan

### Tareas sin Frame.io
- `En curso`/`Cambios Solicitados` -> `Listo para revision` abre una ronda
- `Listo para revision` -> `Cambios Solicitados` o `Listo` cierra sin incrementar

## Limitaciones conocidas

- `Cambios Solicitados -> Changes requested` no es confiable todavia (ver `BUG-006`)
- El webhook no incluye `comment.completed` / `comment.uncompleted` todavia
- No existe `Last Frame Comment By` porque el payload no trae actor enriquecido

## GitHub workflow

- Desarrollar en feature branches, no directo en `main`
- Validar antes de mergear; usar `CHANGELOG.md` con `[Unreleased]`
- Crear tag anotado al publicar: `git tag -a vX.Y.Z -m "descripcion"`
- Si algo falla: apagar feature flag primero, revertir PR si es necesario

## Documentacion interna

- [CHANGELOG.md](CHANGELOG.md) - cambios por version
- [BUGS.md](BUGS.md) - registro de bugs
- [TASKS.md](TASKS.md) - backlog de tareas
- [HANDOFF.md](HANDOFF.md) - traspasos entre agentes
- [project_context.md](project_context.md) - contexto operativo completo
