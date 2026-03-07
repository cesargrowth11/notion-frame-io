#!/usr/bin/env python3
"""
Frame.io V4 — Status Field Discovery
=====================================
Ejecuta este script UNA VEZ para obtener los UUIDs de los
status fields que necesitas configurar en la Cloud Function.

Uso:
  export FRAMEIO_ACCESS_TOKEN="tu-token"
  export FRAMEIO_ACCOUNT_ID="tu-account-id"
  export FRAMEIO_PROJECT_ID="tu-project-id"
  python3 get_frameio_status_uuids.py
"""

import os
import sys
import json
import requests

TOKEN = os.environ.get("FRAMEIO_ACCESS_TOKEN")
ACCOUNT_ID = os.environ.get("FRAMEIO_ACCOUNT_ID")
PROJECT_ID = os.environ.get("FRAMEIO_PROJECT_ID")

if not all([TOKEN, ACCOUNT_ID, PROJECT_ID]):
    print("❌ Faltan variables de entorno:")
    print("   export FRAMEIO_ACCESS_TOKEN='...'")
    print("   export FRAMEIO_ACCOUNT_ID='...'")
    print("   export FRAMEIO_PROJECT_ID='...'")
    sys.exit(1)

BASE = "https://api.frame.io/v4"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}


def get_metadata_fields():
    """Fetch all metadata field definitions for the project."""
    url = f"{BASE}/accounts/{ACCOUNT_ID}/projects/{PROJECT_ID}/metadata/fields"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main():
    print("🔍 Consultando metadata fields de Frame.io V4...\n")

    try:
        result = get_metadata_fields()
    except requests.exceptions.HTTPError as e:
        print(f"❌ Error de API: {e}")
        if e.response:
            print(f"   Status: {e.response.status_code}")
            print(f"   Body: {e.response.text[:500]}")
        sys.exit(1)

    # El response puede tener diferentes estructuras
    fields = result if isinstance(result, list) else result.get("data", result.get("fields", []))

    if not fields:
        print("⚠️  No se encontraron metadata fields.")
        print(f"   Response completo: {json.dumps(result, indent=2)[:2000]}")
        sys.exit(1)

    print(f"📋 Encontrados {len(fields)} metadata fields:\n")
    print("=" * 70)

    status_fields = []

    for field in fields:
        field_id = field.get("id", "N/A")
        field_name = field.get("name", field.get("display_name", "Sin nombre"))
        field_type = field.get("type", field.get("field_type", "unknown"))

        print(f"\n📌 Field: {field_name}")
        print(f"   ID: {field_id}")
        print(f"   Type: {field_type}")

        # Buscar opciones de status
        options = field.get("options", field.get("values", field.get("choices", [])))
        if options:
            print(f"   Opciones ({len(options)}):")
            for opt in options:
                opt_id = opt.get("id", opt.get("uuid", "N/A"))
                opt_name = opt.get("name", opt.get("display_name", opt.get("label", "Sin nombre")))
                opt_color = opt.get("color", "")
                color_str = f" (color: {opt_color})" if opt_color else ""
                print(f"     • {opt_name}: {opt_id}{color_str}")

            status_fields.append({
                "field_id": field_id,
                "field_name": field_name,
                "options": options
            })

    print("\n" + "=" * 70)

    if status_fields:
        print("\n✅ VALORES PARA TUS VARIABLES DE ENTORNO:\n")
        print("# Copia estos valores en tu configuración de Cloud Function")
        print(f"FRAMEIO_STATUS_FIELD_ID={status_fields[0]['field_id']}")
        print()
        print("# Mapea estos UUIDs según tus status de Notion:")
        for opt in status_fields[0].get("options", []):
            opt_id = opt.get("id", opt.get("uuid", "???"))
            opt_name = opt.get("name", opt.get("display_name", "???"))
            print(f"# {opt_name} → {opt_id}")

        print("\n# Ejemplo para .env.yaml:")
        print("# FRAMEIO_STATUS_IN_PROGRESS: '<uuid-de-in-progress>'")
        print("# FRAMEIO_STATUS_NEEDS_REVIEW: '<uuid-de-needs-review>'")
        print("# FRAMEIO_STATUS_APPROVED: '<uuid-de-approved>'")
        print("# FRAMEIO_STATUS_FINAL: '<uuid-de-final>'")
    else:
        print("\n⚠️  No se encontraron fields con opciones.")
        print("   Puede que el proyecto no tenga custom fields de status configurados.")
        print(f"\n   Full response:\n{json.dumps(result, indent=2)[:3000]}")


if __name__ == "__main__":
    main()
