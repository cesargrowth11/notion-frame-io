# Notion <-> Frame.io V4 Sync

Cloud Function para sincronizar estados y señales de revision entre la base `Tareas` de Notion y un proyecto de Frame.io.

## Estado actual

- `Notion -> Frame.io`: funcional para `En curso`
- `Frame.io -> Notion`: funcional para versiones, comentarios y senales base de revision
- `Frame.io -> Notion Comments`: funcional en produccion para `comment.created`
- `Client Change Round`: ajustado y validado en staging branch para contar rondas por version y no por reaperturas sobre la misma version; pendiente merge a `main`
- `Cambios Solicitados -> Changes requested`: no confiable todavia, ver `BUG-006`

## Que hace hoy

### 1. Notion -> Frame.io

Cuando cambia `Estado` en Notion, la funcion intenta actualizar el campo `Status` del asset en Frame.io.

### Asociacion actual de la tarea con el asset

- el input manual inicial sigue siendo `URL Frame.io`
- desde esa URL la funcion intenta extraer o resolver el `asset_id`
- una vez identificado, la funcion cachea `Frame Asset ID` en la pagina de Notion
- en runtime, `Frame Asset ID` se conserva como referencia tecnica estable para no depender siempre de reparsear la URL
- por seguridad operativa, no se cambio la precedencia actual mientras el flujo productivo siga funcionando

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
- opcionalmente publica un comentario page-level en Notion cuando `NOTION_ENABLE_FRAME_COMMENT_MIRROR=true` y el evento es `comment.created`
  - el comentario espejado se formatea con rich text legible y conserva emojis si vienen en el comentario original
  - el formatter preserva saltos de linea para que el comentario no colapse en una sola linea

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
| `Last Reviewed Version` | Number | Ultima version que ya abrio una ronda contabilizada |
| `Client Review Open` | Checkbox | Indica si la ronda sigue abierta |
| `Client Change Round` | Number | Contador persistente de rondas por version |

### Logica actual de `Client Change Round`

- abre una ronda con el primer `comment.created` de una version que aun no tenia ronda contabilizada
- comentarios adicionales, cierres o reaperturas sobre esa misma version no incrementan el contador
- cierra la ronda con `file.versioned`
- si una pagina ya arrastra un `Client Change Round` mayor que `Last Reviewed Version` por la logica anterior, el runtime la autocorrige al proximo procesamiento
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
- `NOTION_ENABLE_FRAME_COMMENT_MIRROR`

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

## GitHub workflow y rollback

- no desarrollar features directo sobre `main`
- crear una rama por feature, por ejemplo `feature/notion-comment-mirror`
- abrir PR hacia `main` solo despues de validar sintaxis, smoke tests y documentacion
- mergear a `main` solo cuando el feature flag este apagado por defecto y el comportamiento actual siga intacto
- usar `CHANGELOG.md` en `Unreleased` mientras la feature no este liberada
- crear tag solo al publicar una version estable, por ejemplo `v2.3.2`
- si algo falla, primero apagar el feature flag y luego revertir el PR si hace falta

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
- aunque la URL es el input manual inicial, el runtime actual conserva `Frame Asset ID` como referencia estable para evitar regresiones si la URL cambia o queda desactualizada
- el mirror de comentarios hacia Notion Comments ya fue validado y quedo habilitado en produccion para `comment.created`

## Documentacion operativa

- Ver [CHANGELOG.md](CHANGELOG.md) para cambios por version
- Ver [BUGS.md](BUGS.md) para causas raiz y resoluciones
- Ver [TASKS.md](TASKS.md) para pendientes activos
- Ver [HANDOFF.md](HANDOFF.md) para traspasos operativos
- Ver [project_context.md](project_context.md) para contexto del proyecto
