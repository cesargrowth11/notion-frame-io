# Notion ↔ Frame.io V4 Bidirectional Sync — V2

**Efeonce Group — Globe Studio Pipeline**

Cloud Function que sincroniza automáticamente el status y métricas de assets entre Notion y Frame.io V4.

## Qué hace

### Flujo 1: Notion → Frame.io (status sync)
Cuando alguien cambia el **Estado** de una tarea en Notion, Frame.io se actualiza automáticamente.

### Flujo 2: Frame.io → Notion (push de métricas)
Cuando alguien sube una nueva versión o deja un comentario en Frame.io, Notion se actualiza con el conteo.

### Flujo 3: Pull en cambio de status
Cuando Notion dispara el webhook de status, la función también trae de vuelta los conteos de Frame.io a Notion (ida y vuelta en la misma ejecución).

## Arquitectura

```
                          ┌─────────────────────────┐
  ┌────────────┐  POST    │                         │  PATCH    ┌────────────┐
  │            │─────────►│   Cloud Function (GCP)  │──────────►│            │
  │  Notion DB │          │   /notion-webhook       │           │ Frame.io   │
  │  "Tareas"  │◄─────────│                         │◄──────────│ V4 API     │
  │            │  UPDATE   │   /frameio-webhook      │  GET      │            │
  └────────────┘  counts  └─────────────────────────┘  counts   └────────────┘
```

## Mapping de Status

| Notion (Estado)        | →  | Frame.io             |
|------------------------|----|----------------------|
| En curso               | →  | In Progress          |
| Listo para revisión    | →  | Needs Review         |
| Cambios Solicitados    | →  | Changes Requested    |
| Listo                  | →  | Approved / Final     |

## Propiedades en Notion (Base "Tareas")

| Propiedad        | Tipo    | Descripción                                    |
|------------------|---------|------------------------------------------------|
| Estado           | Status  | Trigger del sync (ya existía)                  |
| URL Frame.io     | URL     | Los chicos pegan la URL del asset aquí         |
| Frame Versions   | Number  | Versiones en el Version Stack (automático)     |
| Frame Comments   | Number  | Comentarios del asset (automático)             |

> **RpA (Rounds per Asset):** Frame Versions alimenta directamente el cálculo de RpA.
> Tu fórmula de Semáforo RpA puede leer de Frame Versions para tener datos
> automáticos desde Frame.io, complementando la base de Revisiones manual.

## Setup Paso a Paso

### 1. Obtener credenciales de Frame.io V4

1. Ve a [Adobe Developer Console](https://console.adobe.io)
2. Crea un proyecto o usa uno existente
3. Agrega la API de Frame.io
4. Genera un OAuth 2.0 access token
5. Anota tu **Account ID** y **Project ID** (están en la URL de Frame.io)

### 2. Obtener los UUIDs de status de Frame.io

```bash
export FRAMEIO_ACCESS_TOKEN="tu-token"
export FRAMEIO_ACCOUNT_ID="tu-account-id"
export FRAMEIO_PROJECT_ID="tu-project-id"

python3 get_frameio_status_uuids.py
```

### 3. Completar variables de entorno

Edita `.env.yaml` — los valores de Notion ya están pre-configurados:

```yaml
# Ya configurado:
NOTION_TOKEN: "ntn_..."
NOTION_DATABASE_ID: "3a54f0904be14158833533ba96557a73"

# Completar con tus valores de Frame.io:
FRAMEIO_ACCESS_TOKEN: "tu-token"
FRAMEIO_ACCOUNT_ID: "tu-account-id"
FRAMEIO_PROJECT_ID: "tu-project-id"
FRAMEIO_STATUS_FIELD_ID: "uuid-del-campo"
FRAMEIO_STATUS_IN_PROGRESS: "uuid"
FRAMEIO_STATUS_NEEDS_REVIEW: "uuid"
FRAMEIO_STATUS_CHANGES_REQUESTED: "uuid"
FRAMEIO_STATUS_APPROVED: "uuid"
```

### 4. Deploy a Google Cloud

```bash
chmod +x deploy.sh
./deploy.sh
```

Al final te da la URL pública. Ejemplo: `https://us-central1-efeonce-group.cloudfunctions.net/notion-frameio-sync`

### 5. Configurar Notion Automation

1. Abre la base **"Tareas"** en Notion
2. Clic en ⚡️ (Automations)
3. **Trigger:** "Estado" cambia a cualquier valor
4. **Action:** "Send webhook"
5. **URL:** `https://TU-URL/notion-webhook`
6. **Propiedades a enviar:** "URL Frame.io" + "Estado"

### 6. Configurar Frame.io Webhook (opcional, para push)

En el [Frame.io Developer Portal](https://developer.frame.io):

1. Crea un webhook para tu Team/Workspace
2. **URL:** `https://TU-URL/frameio-webhook`
3. **Events:** `file.created`, `comment.created`

### 7. Los chicos pegan URLs

Para cada tarea en Notion que tenga un asset en Frame.io, pegan la URL del navegador en **"URL Frame.io"**:

```
https://app.frame.io/player/a7e95254-8cd6-4d59-b54d-28c58570a8de
```

Cualquier formato de URL de Frame.io funciona (player, reviews, projects).

## Testing

### Health check:
```bash
curl https://TU-URL
```

### Simular webhook de Notion:
```bash
curl -X POST https://TU-URL/notion-webhook \
  -H "Content-Type: application/json" \
  -d '{
    "data": {
      "URL Frame.io": {
        "type": "url",
        "url": "https://app.frame.io/player/TU-ASSET-ID"
      },
      "Estado": {
        "type": "status",
        "status": {"name": "Listo"}
      }
    }
  }'
```

## RpA: Cómo conectar Frame Versions al semáforo

Opción 1 — **Complementar el RpA actual:** Tu fórmula de RpA sigue leyendo del rollup de Revisiones, y Frame Versions sirve como dato de validación cruzada.

Opción 2 — **Reemplazar con Frame Versions:** Cambia la fórmula de RpA para que lea de `prop("Frame Versions")` en vez del rollup. Así el dato viene 100% automático desde Frame.io.

## Endpoints

| Método | Path              | Descripción                           |
|--------|-------------------|---------------------------------------|
| GET    | /                 | Health check + estado de mapping      |
| POST   | /notion-webhook   | Notion → Frame.io + pull counts       |
| POST   | /frameio-webhook  | Frame.io → Notion counts              |

## Consideraciones

- **OAuth Token Refresh:** Los tokens de Frame.io V4 expiran. Para producción, implementar refresh automático o regenerar manualmente.
- **Múltiples proyectos:** Si Globe Studio maneja varios proyectos en Frame.io, agregar lógica de ruteo por proyecto.
- **Rate limits:** Frame.io tiene rate limiting progresivo. Con el volumen de Globe Studio no debería haber problemas.
- **Logs:** Todos los eventos se logean en Cloud Logging de GCP (`notion-frameio-sync`).

## Archivos

```
├── main.py                      # Cloud Function principal (V2 bidireccional)
├── requirements.txt             # Dependencias Python
├── .env.yaml                    # Variables de entorno (Notion pre-configurado)
├── deploy.sh                    # Script de deploy a GCP
├── get_frameio_status_uuids.py  # Helper: obtener UUIDs de Frame.io
└── README.md                    # Este archivo
```
