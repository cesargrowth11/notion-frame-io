# Changelog

Todos los cambios relevantes de este proyecto se documentan aqui.

---

## [2.2.0] - 2026-03-07

### Agregado
- **Resolucion de URLs acortadas**: Soporte para URLs `f.io/xxx` y `fio.co/xxx` via HTTP HEAD con `allow_redirects=True` para resolver la URL final antes de extraer el asset ID.
- **Soporte para URLs de vista**: Manejo de URLs `next.frame.io/project/.../view/...` donde el view ID no es un asset ID. Se busca el asset recorriendo los children del proyecto.
- **Fallback de busqueda por proyecto**: Si la URL contiene "frame.io" pero no matchea ningun patron conocido, se recorre el arbol de assets del proyecto (hasta 2 niveles) comparando `view_url` y `original_url` contra la URL de Notion.
- Funciones internas: `_resolve_short_url()`, `_search_project_for_url()`, `_search_children_for_url()`.

---

## [2.1.0] - 2026-03-07

### Agregado
- **Auto-refresh de tokens OAuth**: Cuando Frame.io responde 401, el sistema automaticamente intercambia el `refresh_token` por un nuevo `access_token` via Adobe IMS (`/ims/token/v3`).
- **Persistencia de tokens**: Los nuevos tokens se persisten en las variables de entorno de la Cloud Function via la API de Google Cloud Functions v2, evitando perder el token en el proximo cold start.
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
- **Flujo 1 (Notion -> Frame.io)**: Cambio de status en Notion dispara webhook que actualiza el status del asset en Frame.io via metadata values API (V4).
- **Flujo 2 (Frame.io -> Notion)**: Webhook de Frame.io (`file.created`, `comment.created`) actualiza conteos de versiones y comentarios en Notion.
- **Flujo 3 (Pull on status change)**: Al cambiar status en Notion, tambien se traen los conteos de Frame.io de vuelta a Notion en la misma ejecucion.
- Parser de URLs de Frame.io con soporte para multiples formatos: player, reviews, projects, asset directo.
- Conteo inteligente de versiones: detecta version stacks y suma versiones de todos los children.
- Conteo de comentarios: suma `comment_count` de todas las versiones en un version stack.
- Mapeo de 4 status: En curso, Listo para revision, Cambios Solicitados, Listo.
- Health check en GET `/` con estado del mapping y version.
- Respuesta 200 con `{"skipped": true}` cuando la tarea no tiene URL de Frame.io (evita que Notion pause la automatizacion).
- Script `deploy.sh` para deploy a GCP con un solo comando.
- Script `generate_frameio_token.py` para generar tokens OAuth de Frame.io V4.
- Script `get_frameio_status_uuids.py` para descubrir UUIDs de metadata fields.

### Infraestructura
- Google Cloud Function 2nd Gen, Python 3.12, region `us-central1`.
- Proyecto GCP: `efeonce-group`.
- URL publica: `https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync`.
