# Changelog

Todos los cambios relevantes de este proyecto se documentan aqui.

---

## [Unreleased]

### Cambiado
- [BUG-007] `Client Change Round` en la branch `feature/client-change-round-version-logic` ahora cuenta una sola ronda por version entregada: comentarios adicionales, cierres o reaperturas sobre la misma version ya no incrementan el contador.
- [BUG-007] `Last Reviewed Version` pasa a representar la ultima version que ya abrio una ronda contabilizada, en lugar de adelantarse automaticamente a la ultima version vista.
- [BUG-007] El runtime ahora autocorrige paginas heredadas donde `Client Change Round` quedo mayor que `Last Reviewed Version` por la logica anterior.
- La branch `feature/notion-workflow-change-rounds` agrega una rama `workflow_only` en `/notion-webhook` para tareas sin `Frame Asset ID`, usando `Estado` y `Review Source` para alimentar `Workflow Change Round`, `Workflow Review Open` y `Last Workflow Status`.
- La logica de workflow-only bootstrappea la primera ronda en `1` cuando una tarea preexistente entra por primera vez a `Listo para revision` con campos auxiliares vacios, y evita dobles incrementos en webhooks repetidos mientras la revision sigue abierta.
- La branch `feature/frameio-comment-version-attribution` agrega resolucion de `Version N` para comentarios de Frame.io a partir de `comment.file_id` y el orden actual del version stack, y prepara la propiedad `Last Frame Comment Version` junto con la metadata `Version: N` en comentarios espejados.

### Documentacion
- Se alinearon `README.md`, `project_context.md` y `BUGS.md` con la nueva semantica version-based de `Client Change Round` antes de validar el branch para merge.
- Se agrego trazabilidad explicita de que la fix fue validada en staging y sigue pendiente de merge a `main`.
- Se actualizo la documentacion del plan Notion-only a estado implementado en branch, incluyendo la validacion real en staging sobre la secuencia `En curso -> Listo para revision -> Cambios Solicitados -> Listo para revision`.
- Se documento la factibilidad tecnica y el plan exacto para atribuir `Version N` a comentarios de Frame.io usando `comment.file_id` y la posicion del file dentro del version stack, con rollout inicial limitado al ultimo comentario y al comentario espejado en Notion.
- Se registro como deuda tecnica separada la discrepancia entre llamadas locales directas a Frame.io (`403`) y las mismas lecturas realizadas desde la Cloud Function, para investigarla antes de volver a depender de diagnosticos locales contra la API.
- Se dejo trazabilidad de que la feature de atribucion de version quedo mergeada y desplegada a produccion, con validacion real de `Last Frame Comment Version = 1` y seguimiento pendiente para el primer caso real de `Version > 1`.

## [2.3.2] - 2026-03-07

### Agregado
- [BUG-004] **Propiedad explicita `Frame Asset ID` en Notion**: el backend ahora puede leer y persistir un UUID de asset dedicado para enlazar Frame.io -> Notion sin depender solo de la URL.
- **Senales de revision para RpA**: nuevas propiedades de Notion para `Open Frame Comments`, `Resolved Frame Comments`, `Last Frame Comment`, `Last Frame Comment ID`, `Last Frame Comment At`, `Last Frame Comment Timecode`, `Last Reviewed Version`, `Client Review Open` y `Client Change Round`.
- **Mirror opcional de comentarios a Notion Comments**: nuevo feature flag `NOTION_ENABLE_FRAME_COMMENT_MIRROR` para publicar `comment.created` como comentario page-level en Notion sin reemplazar el sync estructurado existente.

### Cambiado
- [BUG-004] `notion_find_page()` ahora intenta buscar primero por `Frame Asset ID` y usa `URL Frame.io` solo como fallback.
- [BUG-004] `parse_notion_payload()` ahora acepta `Frame Asset ID` en el payload de Notion antes de intentar parsear la URL.
- [BUG-004] Al actualizar `Frame Versions` y `Frame Comments`, la funcion tambien intenta cachear `Frame Asset ID` en la pagina si el schema lo permite.
- `handle_frameio()` ahora resuelve `file_id` desde `comment_id` para eventos `comment.*` usando `GET /v4/accounts/{account_id}/comments/{comment_id}`.
- [BUG-005] `fio_get_counts()` ahora toma `Comment Count` desde metadata V4 tolerando `data` como lista u objeto, y deja V2 como apoyo para la logica de versiones.
- **Review-round sync**: `GET /files/{file_id}/comments` ahora alimenta senales de revision en Notion y una primera logica persistente de `Client Change Round`.
- [BUG-006] `Cambios Solicitados` sigue sin considerarse una senal confiable de ronda; el contador usa `comment.created` como apertura y `file.versioned` como cierre de ronda.
- **UI del mirror de comentarios**: el comentario espejado hacia Notion ahora usa rich text con negritas en encabezado y metadatos utiles, y conserva emojis/texto tal como llegan desde Frame.io.
- **Fix de formato del mirror**: los saltos de linea del comentario espejado ya no se eliminan al construir `rich_text`, evitando que todo quede en una sola linea en Notion.

### Infraestructura
- Webhook de Frame.io creado en el workspace `c90b7046-2ad9-4097-bcb4-3a81ee239398` apuntando a `/frameio-webhook`.
- Eventos suscritos: `file.created`, `file.versioned`, `comment.created`, `comment.deleted`.
- [BUG-003] Se agrego `roles/secretmanager.secretAccessor` a la service account de la Cloud Function para leer tokens desde Secret Manager en cold start.

### Documentacion
- `README.md` y `project_context.md` se alinearon con el modelo actual: Secret Manager, `Frame Asset ID`, senales de comentarios, `Client Change Round`, y el hecho de que `RpA` y `Semaforo RpA` siguen siendo calculados en Notion.
- `BUGS.md` se consolido como registro operativo para referenciar causas, resoluciones y estado de bugs desde este changelog.
- Se aclaro explicitamente que `URL Frame.io` sigue siendo el input manual inicial y que `Frame Asset ID` se conserva como cache tecnico estable; no se cambio la logica del runtime para evitar regresiones.
- Se documento un workflow de branches, PRs, feature flags y rollback para evitar empujar features nuevos directo a `main`.

---

## [2.3.1] - 2026-03-07

### Cambiado
- [BUG-003] **Persistencia de tokens migrada a Secret Manager**: reemplaza `_update_cloud_function_env()` (que fallaba con 403) por `_read_secret()` y `_write_secret()` usando Google Cloud Secret Manager.
- [BUG-003] Los tokens se cargan desde Secret Manager al cold start (`_load_tokens_from_secrets()`), con fallback a env vars.
- [BUG-003] Al refrescar tokens via Adobe IMS, se persisten como nuevas versiones en Secret Manager.
- Secrets: `frameio-access-token`, `frameio-refresh-token`.
- Dependencia: `google-cloud-secret-manager>=2.0` reemplaza `google-cloud-functions>=1.0`.

### Eliminado
- `_update_cloud_function_env()`: ya no se actualizan env vars de la Cloud Function via GCP API.
- Variables `_GCF_FUNCTION_NAME`, `_GCF_REGION`: ya no son necesarias.

---

## [2.3.0] - 2026-03-07

### Agregado
- **Patron explicito para `next.frame.io`**: nueva regex `next\.frame\.io/project/[^/]+/view/([a-f0-9\-]{36})` que extrae el asset ID directamente del final de URLs de vista. Confirmado con asset `DRYP_30_FINAL_9x16.mp4` (ID: `7f289cd4-b30e-4103-91c8-48042497683a`).
- [BUG-001] **Normalizacion Unicode de status**: funcion `_normalize_text()` que elimina acentos y normaliza espacios/mayusculas antes de comparar status. Esto permite que `Listo para revision` matchee con `Listo para revision` con o sin tilde.
- [BUG-001] **Mapa de status normalizado**: `_NORMALIZED_STATUS_MAP` pre-computa las claves normalizadas al inicio para evitar recalcular en cada request.
- [BUG-001] **Funcion `_status_uuid_for()`**: reemplaza la comparacion directa `status in STATUS_MAP` por busqueda normalizada.
- [BUG-002] **Recuperacion de propiedades faltantes**: `notion_get_page()` obtiene la pagina completa de Notion cuando el webhook no incluye todas las propiedades, por ejemplo si falta URL o status.
- [BUG-002] **Parser de payload mejorado**: `parse_notion_payload()` ahora busca propiedades en `data` y tambien en `data.properties` como fallback, cubriendo mas formatos de webhook.
- Documentacion: `project_context.md` y `CHANGELOG.md`.

### Cambiado
- [BUG-002] `handle_notion()` ahora intenta recuperar `asset_id` y `status` via API de Notion si el webhook no los incluye.
- [BUG-001] El matching de status usa `_status_uuid_for()` en lugar de acceso directo a `STATUS_MAP`.

---

## [2.2.0] - 2026-03-07

### Agregado
- **Resolucion de URLs acortadas**: soporte para URLs `f.io/xxx` y `fio.co/xxx` via HTTP HEAD con `allow_redirects=True` para resolver la URL final antes de extraer el asset ID.
- **Soporte para URLs de vista**: manejo de URLs `next.frame.io/project/.../view/...` donde el view ID no es un asset ID. Se busca el asset recorriendo los children del proyecto.
- **Fallback de busqueda por proyecto**: si la URL contiene `frame.io` pero no matchea ningun patron conocido, se recorre el arbol de assets del proyecto hasta 2 niveles comparando `view_url` y `original_url` contra la URL de Notion.
- Funciones internas: `_resolve_short_url()`, `_search_project_for_url()`, `_search_children_for_url()`.

---

## [2.1.0] - 2026-03-07

### Agregado
- **Auto-refresh de tokens OAuth**: cuando Frame.io responde 401, el sistema automaticamente intercambia el `refresh_token` por un nuevo `access_token` via Adobe IMS (`/ims/token/v3`).
- **Persistencia de tokens**: los nuevos tokens se persisten en las variables de entorno de la Cloud Function via la API de Google Cloud Functions v2, evitando perder el token en el proximo cold start.
- Wrapper `_fio_request()` que encapsula todas las llamadas a Frame.io con retry automatico en 401.
- Funcion `_refresh_access_token()` para el flujo OAuth con Adobe IMS.
- Funcion `_update_cloud_function_env()` para persistir tokens via GCP API.
- Nuevas variables de entorno: `FRAMEIO_REFRESH_TOKEN`, `FRAMEIO_CLIENT_ID`, `FRAMEIO_CLIENT_SECRET`.
- Dependencia: `google-cloud-functions>=1.0` en `requirements.txt`.

### Cambiado
- Todas las llamadas a la API de Frame.io ahora pasan por `_fio_request()` en lugar de `requests` directo.

---

## [2.0.0] - 2026-03-07

### Agregado
- **Sync bidireccional completo** entre Notion y Frame.io V4.
- **Flujo 1 (Notion -> Frame.io)**: cambio de status en Notion dispara webhook que actualiza el status del asset en Frame.io via metadata values API (V4).
- **Flujo 2 (Frame.io -> Notion)**: webhook de Frame.io (`file.created`, `comment.created`) actualiza conteos de versiones y comentarios en Notion.
- **Flujo 3 (Pull on status change)**: al cambiar status en Notion, tambien se traen los conteos de Frame.io de vuelta a Notion en la misma ejecucion.
- Parser de URLs de Frame.io con soporte para multiples formatos: player, reviews, projects y asset directo.
- Conteo inteligente de versiones: detecta version stacks y suma versiones de todos los children.
- Conteo de comentarios: suma `comment_count` de todas las versiones en un version stack.
- Mapeo de 4 status: `En curso`, `Listo para revision`, `Cambios Solicitados`, `Listo`.
- Health check en `GET /` con estado del mapping y version.
- Respuesta 200 con `{"skipped": true}` cuando la tarea no tiene URL de Frame.io, evitando que Notion pause la automatizacion.
- Script `deploy.sh` para deploy a GCP con un solo comando.
- Script `generate_frameio_token.py` para generar tokens OAuth de Frame.io V4.
- Script `get_frameio_status_uuids.py` para descubrir UUIDs de metadata fields.

### Infraestructura
- Google Cloud Function 2nd Gen, Python 3.12, region `us-central1`.
- Proyecto GCP: `efeonce-group`.
- URL publica: `https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync`.
