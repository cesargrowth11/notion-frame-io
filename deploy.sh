#!/bin/bash
# ─────────────────────────────────────────────────────────
# Deploy: Notion → Frame.io Status Sync
# Google Cloud Function (2nd Gen)
#
# Efeonce Group — Globe Studio Pipeline
# ─────────────────────────────────────────────────────────
#
# Prerequisitos:
#   1. gcloud CLI instalado y autenticado
#   2. Proyecto GCP configurado (efeonce-group)
#   3. .env.yaml completado con valores reales
#   4. APIs habilitadas: Cloud Functions, Cloud Build, Cloud Run
#
# Uso:
#   chmod +x deploy.sh
#   ./deploy.sh
# ─────────────────────────────────────────────────────────

set -e

# ── Config ──
PROJECT_ID="efeonce-group"
REGION="us-central1"
FUNCTION_NAME="notion-frameio-sync"
ENTRY_POINT="sync_status"
RUNTIME="python312"

echo "🚀 Deploying ${FUNCTION_NAME} to ${PROJECT_ID}..."
echo ""

# ── Set project ──
gcloud config set project ${PROJECT_ID}

# ── Enable required APIs (idempotent) ──
echo "📦 Verificando APIs habilitadas..."
gcloud services enable cloudfunctions.googleapis.com --quiet
gcloud services enable cloudbuild.googleapis.com --quiet
gcloud services enable run.googleapis.com --quiet

# ── Deploy ──
echo ""
echo "☁️  Deploying Cloud Function..."
echo ""

gcloud functions deploy ${FUNCTION_NAME} \
  --gen2 \
  --region=${REGION} \
  --runtime=${RUNTIME} \
  --source=. \
  --entry-point=${ENTRY_POINT} \
  --trigger-http \
  --allow-unauthenticated \
  --env-vars-file=.env.yaml \
  --memory=256MB \
  --timeout=60s \
  --min-instances=0 \
  --max-instances=10

echo ""
echo "✅ Deploy completado!"
echo ""

# ── Get URL ──
FUNCTION_URL=$(gcloud functions describe ${FUNCTION_NAME} \
  --gen2 \
  --region=${REGION} \
  --format='value(serviceConfig.uri)')

echo "═══════════════════════════════════════════════════"
echo "📌 URL de tu Cloud Function:"
echo ""
echo "   ${FUNCTION_URL}"
echo ""
echo "═══════════════════════════════════════════════════"
echo ""
echo "📋 Próximos pasos:"
echo "   1. Copia la URL de arriba"
echo "   2. Ve a tu base de datos en Notion"
echo "   3. Crea una Database Automation:"
echo "      Trigger: Status cambia a cualquier valor mapeado"
echo "      Action: Send Webhook → pega la URL"
echo "      Incluye propiedades: 'Frame Asset ID' + 'Status'"
echo ""
echo "🧪 Test rápido:"
echo "   curl ${FUNCTION_URL}"
echo ""
