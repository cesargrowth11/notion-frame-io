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
| `Last Frame Comment Version` | Number | Version inferida del ultimo comentario dentro del version stack |
| `Last Reviewed Version` | Number | Ultima version que ya abrio una ronda contabilizada |
| `Client Review Open` | Checkbox | Indica si la ronda sigue abierta |
| `Client Change Round` | Number | Contador persistente de rondas por version |

### Logica actual de `Client Change Round`

- abre una ronda con el primer `comment.created` de una version que aun no tenia ronda contabilizada
- comentarios adicionales, cierres o reaperturas sobre esa misma version no incrementan el contador
- cierra la ronda con `file.versioned`
- si una pagina ya arrastra un `Client Change Round` mayor que `Last Reviewed Version` por la logica anterior, el runtime la autocorrige al proximo procesamiento
- no usa `Cambios Solicitados` como senal principal mientras `BUG-006` siga abierto

### Workflow-backed rounds para piezas que no pasan por Frame.io

No todas las piezas van a revisarse en Frame.io. Para PDFs, brochures, landing pages u otros entregables revisados por otros canales, esta branch implementa una logica paralela en la Cloud Function para contar rondas desde transiciones de `Estado`, sin depender de automations complejas de Notion.

Estado de la implementacion en la branch `feature/notion-workflow-change-rounds`:
- tareas con `Frame Asset ID` siguen usando la logica actual de Frame.io
- tareas sin `Frame Asset ID` y con `Review Source = Workflow` o `Auto` entran por una rama `workflow_only` en `/notion-webhook`
- el backend escribe `Workflow Change Round`, `Workflow Review Open` y `Last Workflow Status`
- `Review Source` permite forzar `Frame.io`, forzar `Workflow` o dejar `Auto`

Propiedades de soporte:
- `Workflow Change Round`
- `Workflow Review Open`
- `Last Workflow Status`
- `Review Source`

Regla de negocio aplicada para tareas sin Frame.io:
- `En curso` o `Cambios Solicitados` -> `Listo para revision` abre una nueva ronda
- `Listo para revision` -> `Cambios Solicitados` no incrementa la ronda, solo la devuelve a trabajo
- `Listo para revision` -> `Listo` cierra la revision sin incrementar
- una tarea preexistente con campos auxiliares vacios se auto-inicializa en ronda `1` cuando entra por primera vez a `Listo para revision`
- repetir el mismo webhook mientras la tarea sigue en revision no vuelve a incrementar la ronda

Validacion real en staging:
- pagina de prueba `31c39c2f-efe7-811a-9b6e-f40938fd0946`
- secuencia validada: `En curso` -> `Listo para revision` -> `Cambios Solicitados` -> `Listo para revision`
- resultado observado: `Workflow Change Round = 1 -> 1 -> 2`
- `Workflow Review Open = true -> false -> true`

Pendiente antes de liberarlo:
- agregar `Client Change Round Final`
- mover `RpA` y `Semaforo RpA` a la propiedad final unificada
- decidir si `Revisiones` se usa como bitacora auto-generada o solo como apoyo opcional

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

## Plan documentado: version de cada comentario de Frame.io

Problema:
- hoy el sistema trae comentarios y espeja `comment.created`, pero no indica a que numero de version pertenece cada comentario
- eso vuelve ambiguo el feedback cuando un asset ya tiene varias versiones en su version stack

Factibilidad tecnica confirmada:
- el comentario V4 expone `file_id`
- el file expone `parent_id`
- Frame.io define el version stack como un contenedor ordenado de files y declara que ese orden determina el numero de version
- existe endpoint estable para listar children del version stack

Decision tecnica documentada:
- el numero de version se inferira desde la posicion actual del `file_id` del comentario dentro de los children ordenados del version stack
- el numero sera 1-based (`Version 1`, `Version 2`, etc.)
- ese dato debe tratarse como contexto operativo actual, no como identificador historico inmutable, porque Frame.io permite reordenar el stack

Alcance recomendado de la primera implementacion:
- agregar una propiedad de Notion `Last Frame Comment Version`
- extender `fio_get_comment_signals()` para devolver `last_comment_version`
- extender el mirror de comentarios para mostrar `Version: N` junto al comentario espejado en Notion
- no intentar backfill completo de todos los comentarios en v1

Estado en la branch `feature/frameio-comment-version-attribution`:
- el runtime ya resuelve `Version: N` para el ultimo comentario y para `comment.created`
- `Last Frame Comment Version` se escribe de forma tolerante: si la propiedad no existe todavia en Notion, el patch hace fallback sin romper el sync principal
- el mirror de comentarios ya puede mostrar `Version: N` en la metadata del comentario espejado

Algoritmo propuesto:
1. leer el comentario (`GET /comments/{comment_id}` o listado de comentarios del file)
2. resolver su `file_id`
3. leer ese file y obtener `parent_id`
4. si el parent no es un version stack:
   - tratar el comentario como `Version 1`
5. si el parent es un version stack:
   - listar los children ordenados del stack
   - ubicar la posicion del `file_id` del comentario
   - convertir esa posicion a version 1-based
6. escribir `Last Frame Comment Version` y, si el mirror esta activo, agregar `Version: N` al comentario espejado

Riesgos y limites documentados:
- si el stack se reordena, el numero puede cambiar en recalculos futuros
- calcular la version de todos los comentarios de un asset es mas costoso que calcular solo la del ultimo comentario o la del comentario del webhook
- la primera iteracion deberia limitarse a:
  - ultimo comentario
  - comentario espejado en Notion

## Documentacion operativa

- Ver [CHANGELOG.md](CHANGELOG.md) para cambios por version
- Ver [BUGS.md](BUGS.md) para causas raiz y resoluciones
- Ver [TASKS.md](TASKS.md) para pendientes activos
- Ver [HANDOFF.md](HANDOFF.md) para traspasos operativos
- Ver [project_context.md](project_context.md) para contexto del proyecto
