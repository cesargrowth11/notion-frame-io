# Bug Register

Registro operativo de bugs/issues del proyecto. Cada bug tiene un ID estable para poder referenciarlo desde `CHANGELOG.md`, handoffs y commits.

## Estados

- `open`
- `monitoring`
- `resolved`

## Bugs

| ID | Estado | Reportado | Resuelto | Titulo |
|----|--------|-----------|----------|--------|
| `BUG-001` | resolved | 2026-03-07 | 2026-03-07 | Status de Notion con tildes no sincronizaba a Frame.io |
| `BUG-002` | resolved | 2026-03-07 | 2026-03-07 | Webhook de Notion omitia propiedades y el sync se saltaba |
| `BUG-003` | resolved | 2026-03-07 | 2026-03-07 | Persistencia de tokens fallaba con 403 al intentar mutar env vars de Cloud Function |
| `BUG-004` | resolved | 2026-03-07 | 2026-03-07 | Asociacion Frame.io -> Notion dependia solo de parsear URL |
| `BUG-005` | resolved | 2026-03-07 | 2026-03-07 | Comentarios de Frame.io no se reflejaban en `Frame Comments` de Notion |
| `BUG-006` | open | 2026-03-07 | — | `Cambios Solicitados` reporta `frameio_status: updated` pero no deja el asset en `Changes requested` |

## Detalle

### `BUG-001` Status de Notion con tildes no sincronizaba a Frame.io

- Sintoma:
  - `Listo para revisión` en Notion no hacia match con el mapping del backend.
- Causa raiz:
  - El mapping comparaba texto literal y no normalizaba acentos/espacios.
- Resolucion:
  - Se agrego `_normalize_text()` y `_status_uuid_for()` para normalizar antes del match.
- Referencias:
  - `CHANGELOG.md` `2.3.0`

### `BUG-002` Webhook de Notion omitia propiedades y el sync se saltaba

- Sintoma:
  - Algunos payloads de Notion llegaban sin `Estado` o sin `URL Frame.io`, y la funcion respondia como si la tarea no estuviera lista.
- Causa raiz:
  - `parse_notion_payload()` asumía un shape estrecho del payload.
- Resolucion:
  - Se agrego fallback a `data.properties` y `notion_get_page(page_id)` para recuperar propiedades faltantes.
- Referencias:
  - `CHANGELOG.md` `2.3.0`

### `BUG-003` Persistencia de tokens fallaba con 403 al intentar mutar env vars de Cloud Function

- Sintoma:
  - El refresh OAuth funcionaba de forma momentanea, pero el token nuevo no sobrevivía de forma confiable a siguientes ejecuciones.
- Causa raiz:
  - El enfoque original intentaba persistir tokens actualizando env vars de la Cloud Function y eso fallaba por permisos.
- Resolucion:
  - Los tokens se migraron a Secret Manager.
  - La service account de la funcion recibio `secretVersionManager` y luego `secretAccessor` para leer versiones nuevas en cold start.
- Referencias:
  - `CHANGELOG.md` `2.3.1`

### `BUG-004` Asociacion Frame.io -> Notion dependia solo de parsear URL

- Sintoma:
  - El lookup de la tarea correcta era fragil y dependia de encontrar el UUID dentro de la URL.
- Causa raiz:
  - No existia una propiedad de asociacion explicita entre tarea y asset.
- Resolucion:
  - Se agrego `Frame Asset ID` en la base `Tareas`.
  - El backend ahora busca primero por `Frame Asset ID` y usa `URL Frame.io` como fallback.
- Referencias:
  - `CHANGELOG.md` `Unreleased`

### `BUG-005` Comentarios de Frame.io no se reflejaban en `Frame Comments` de Notion

- Sintoma:
  - Frame.io mostraba comentarios en el asset, el webhook llegaba a la Cloud Function, pero `Frame Comments` seguia en `0` en Notion.
- Causa raiz:
  - `fio_get_counts()` asumía que `GET /v4/accounts/{account_id}/files/{file_id}/metadata` devolvía `data` como lista.
  - En la respuesta real, `data` puede llegar como objeto unico; el parseo dejaba `metadata=[]` y el conteo de comentarios quedaba en `0`.
  - Ademas, la funcion no tenia `secretAccessor` en Secret Manager, lo que dificultaba cargar el token mas reciente al cold start.
- Resolucion:
  - `fio_get_counts()` ahora soporta `data` como lista o como objeto al leer `Comment Count`.
  - Se mantuvo V2 solo para la logica de versiones y se priorizo V4 metadata para comentarios.
  - Se concedio `roles/secretmanager.secretAccessor` a la service account de la funcion para ambos secrets.
- Validacion:
  - La funcion devolvio `counts.comments = 1` en `/frameio-webhook`.
  - La tarea de Notion actualizo `Frame Comments = 1`.
- Referencias:
  - `CHANGELOG.md` `Unreleased`

### `BUG-006` `Cambios Solicitados` reporta `frameio_status: updated` pero no deja el asset en `Changes requested`

- Sintoma:
  - El webhook de Notion responde `frameio_status: updated` para `Estado = Cambios Solicitados`, pero al leer el asset en Frame.io el `Status` sigue en `Needs Review`.
- Causa raiz:
  - Todavia no confirmada. Puede ser un problema del UUID usado para `Changes requested`, del payload aceptado por ese valor concreto, o de una discrepancia entre la API y el valor de metadata.
- Estado actual:
  - No se usa `Cambios Solicitados` como señal principal para `Client Change Round`.
  - La logica de rondas usa `comment.created` y `file.versioned`.
- Referencias:
  - `CHANGELOG.md` `Unreleased`
