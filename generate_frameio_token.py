#!/usr/bin/env python3
"""
Frame.io V4 — OAuth Token Generator
====================================
Ejecuta este script para obtener tu access token de Frame.io V4.

1. Abre la URL que te muestra en tu navegador
2. Inicia sesión con tu Adobe ID
3. Copia la URL COMPLETA a la que te redirige (aunque parezca que no tiene código)
4. Pégala cuando te la pida el script
5. El script intercambia el código por un access token

Uso:
  python3 generate_frameio_token.py
"""

import os
import sys
import json
import urllib.parse
import webbrowser

try:
    import requests
except ImportError:
    print("❌ Necesitas instalar requests: pip install requests")
    sys.exit(1)

# ─── Credentials (from environment variables) ───
CLIENT_ID = os.environ.get("ADOBE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("ADOBE_CLIENT_SECRET", "")
REDIRECT_URI = "https://console.adobe.io"
SCOPES = "openid,email,profile,offline_access,additional_info.roles"

if not CLIENT_ID or not CLIENT_SECRET:
    print("Missing environment variables:")
    print("  export ADOBE_CLIENT_ID='your-client-id'")
    print("  export ADOBE_CLIENT_SECRET='your-client-secret'")
    sys.exit(1)

# ─── Step 1: Build authorization URL ───
auth_url = (
    f"https://ims-na1.adobelogin.com/ims/authorize/v2"
    f"?client_id={CLIENT_ID}"
    f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
    f"&response_type=code"
    f"&scope={urllib.parse.quote(SCOPES)}"
)

print("=" * 60)
print("🔑 Frame.io V4 — OAuth Token Generator")
print("=" * 60)
print()
print("PASO 1: Abre esta URL en tu navegador:")
print()
print(f"  {auth_url}")
print()
print("  (Intentando abrir automáticamente...)")
print()

try:
    webbrowser.open(auth_url)
except Exception:
    pass

print("PASO 2: Inicia sesión con tu Adobe ID")
print()
print("PASO 3: Después del login, serás redirigido.")
print("  Copia la URL COMPLETA de la barra de dirección")
print("  (incluso si parece que no tiene nada especial)")
print()

redirect_url = input("Pega la URL completa aquí: ").strip()

# ─── Step 2: Extract authorization code ───
code = None

# Try to extract from URL parameters
if "code=" in redirect_url:
    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    if "code" in params:
        code = params["code"][0]
    # Also check fragment
    if not code:
        frag_params = urllib.parse.parse_qs(parsed.fragment)
        if "code" in frag_params:
            code = frag_params["code"][0]

# If no code found in URL, maybe they pasted just the code
if not code and not redirect_url.startswith("http"):
    code = redirect_url

if not code:
    print()
    print("❌ No se encontró un código de autorización en la URL.")
    print()
    print("   Intenta copiar la URL INMEDIATAMENTE después del redirect,")
    print("   antes de que la página termine de cargar.")
    print()
    print("   Si la URL se ve así: https://console.adobe.io/?code=eyJ...")
    print("   Copia todo lo que viene después de 'code='")
    print()
    code_direct = input("O pega el código directamente si lo tienes: ").strip()
    if code_direct:
        code = code_direct
    else:
        sys.exit(1)

print()
print(f"✅ Código encontrado: {code[:20]}...")
print()

# ─── Step 3: Exchange code for access token ───
print("📡 Intercambiando código por access token...")
print()

token_url = "https://ims-na1.adobelogin.com/ims/token/v3"
token_data = {
    "grant_type": "authorization_code",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "code": code,
    "redirect_uri": REDIRECT_URI,
}

try:
    resp = requests.post(token_url, data=token_data, timeout=30)
    if resp.status_code == 200:
        token_info = resp.json()
        access_token = token_info.get("access_token", "")
        refresh_token = token_info.get("refresh_token", "")
        expires_in = token_info.get("expires_in", 0)

        print("=" * 60)
        print("✅ ¡TOKEN GENERADO EXITOSAMENTE!")
        print("=" * 60)
        print()
        print(f"ACCESS TOKEN (primeros 50 chars):")
        print(f"  {access_token[:50]}...")
        print()
        print(f"REFRESH TOKEN:")
        print(f"  {refresh_token[:50]}..." if refresh_token else "  (no disponible)")
        print()
        print(f"EXPIRA EN: {expires_in // 3600} horas")
        print()

        # Test the token
        print("🧪 Probando token contra Frame.io API...")
        test_resp = requests.get(
            "https://api.frame.io/v4/accounts",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15
        )
        if test_resp.status_code == 200:
            accounts = test_resp.json()
            print(f"  ✅ Token funciona. Cuentas encontradas:")
            for acc in accounts.get("data", accounts if isinstance(accounts, list) else []):
                acc_id = acc.get("id", "N/A")
                acc_name = acc.get("name", acc.get("display_name", "Sin nombre"))
                print(f"     • {acc_name}: {acc_id}")
        else:
            print(f"  ⚠️ Frame.io respondió {test_resp.status_code}: {test_resp.text[:200]}")

        print()
        print("=" * 60)
        print("📋 PARA TU .env.yaml:")
        print(f'FRAMEIO_ACCESS_TOKEN: "{access_token}"')
        print("=" * 60)

        # Save to file
        with open("frameio_token.json", "w") as f:
            json.dump(token_info, f, indent=2)
        print()
        print("💾 Token completo guardado en: frameio_token.json")

    else:
        print(f"❌ Error al obtener token: {resp.status_code}")
        print(f"   {resp.text[:500]}")
        print()
        print("   Posibles causas:")
        print("   • El código ya expiró (tienes ~5 minutos)")
        print("   • Las credenciales no coinciden")
        print("   • El redirect URI no coincide exactamente")

except Exception as e:
    print(f"❌ Error: {e}")
