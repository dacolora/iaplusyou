"""
Autorización OAuth de una sola vez para Meta (Facebook + Instagram).

Antes de correr esto necesitas (ver SETUP.md para el paso a paso):
  1. Una app en developers.facebook.com con los productos "Facebook Login for Business"
     y "Instagram Graph API" agregados.
  2. META_APP_ID y META_APP_SECRET en tu .env.
  3. En "Facebook Login for Business" > Configuración, agregada la URI de redirección:
     http://localhost:8765/callback
  4. Una Página de Facebook, con una cuenta de Instagram Business/Creator vinculada a ella.

Uso:
    python auth/auth_meta.py                     # cuenta propia (uso de un solo cliente)
    python auth/auth_meta.py --cliente empresa_a  # autoriza la Página/IG de esa empresa

Esto abre el navegador para iniciar sesión, luego te deja elegir la Página, obtiene
un Page Access Token de larga duración y el ID de la cuenta de Instagram vinculada, y
los escribe directamente en el .env correspondiente (clientes/<empresa>/.env si se pasó
--cliente, o el .env de la raíz si no).
"""
import argparse
import os
import re
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
GRAPH_VERSION = "v21.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"
REDIRECT_URI = "http://localhost:8765/callback"
SCOPES = ",".join(
    [
        "pages_show_list",
        "pages_read_engagement",
        "pages_manage_posts",
        "publish_video",
        "instagram_basic",
        "instagram_content_publish",
    ]
)

_captured_code = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _captured_code["code"] = params["code"][0]
            body = b"Autorizado. Ya puedes cerrar esta pestana y volver a la terminal."
        else:
            body = b"No recibi un codigo de autorizacion. Revisa la terminal."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def _wait_for_code():
    server = HTTPServer(("localhost", 8765), _CallbackHandler)
    while "code" not in _captured_code:
        server.handle_request()
    server.server_close()
    return _captured_code["code"]


def _write_env_vars(env_path, values):
    """Actualiza (o agrega) las claves de `values` en env_path, sin tocar el resto del archivo."""
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    remaining = dict(values)
    for i, line in enumerate(lines):
        match = re.match(r"^([A-Z0-9_]+)=", line)
        if match and match.group(1) in remaining:
            key = match.group(1)
            lines[i] = f"{key}={remaining.pop(key)}\n"

    for key, value in remaining.items():
        lines.append(f"{key}={value}\n")

    os.makedirs(os.path.dirname(env_path) or ".", exist_ok=True)
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cliente", help="Nombre de carpeta bajo clientes/, si aplica")
    args = parser.parse_args()

    app_id = os.environ.get("META_APP_ID")
    app_secret = os.environ.get("META_APP_SECRET")
    if not app_id or not app_secret:
        raise RuntimeError("Faltan META_APP_ID / META_APP_SECRET en tu .env")

    auth_url = "https://www.facebook.com/{}/dialog/oauth?{}".format(
        GRAPH_VERSION,
        urlencode(
            {
                "client_id": app_id,
                "redirect_uri": REDIRECT_URI,
                "scope": SCOPES,
                "response_type": "code",
            }
        ),
    )
    print("Abriendo el navegador para autorizar con Facebook...")
    print(f"Si no se abre solo, visita:\n{auth_url}\n")
    webbrowser.open(auth_url)

    code = _wait_for_code()

    token_resp = requests.get(
        f"{GRAPH_URL}/oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
        timeout=30,
    )
    token_resp.raise_for_status()
    short_lived_token = token_resp.json()["access_token"]

    long_resp = requests.get(
        f"{GRAPH_URL}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_lived_token,
        },
        timeout=30,
    )
    long_resp.raise_for_status()
    long_lived_user_token = long_resp.json()["access_token"]

    pages_resp = requests.get(
        f"{GRAPH_URL}/me/accounts",
        params={"access_token": long_lived_user_token},
        timeout=30,
    )
    pages_resp.raise_for_status()
    pages = pages_resp.json().get("data", [])
    if not pages:
        raise RuntimeError(
            "Tu usuario no administra ninguna Página de Facebook. Crea una o pide acceso."
        )

    if len(pages) == 1:
        page = pages[0]
    else:
        print("\nElige la Página de Facebook a usar:")
        for i, p in enumerate(pages):
            print(f"  [{i}] {p['name']} (id: {p['id']})")
        idx = int(input("Número: ").strip())
        page = pages[idx]

    page_id = page["id"]
    page_access_token = page["access_token"]  # ya es de larga duración al venir de un user token largo

    ig_resp = requests.get(
        f"{GRAPH_URL}/{page_id}",
        params={"fields": "instagram_business_account", "access_token": page_access_token},
        timeout=30,
    )
    ig_resp.raise_for_status()
    ig_account = ig_resp.json().get("instagram_business_account")
    ig_user_id = ig_account["id"] if ig_account else None

    if args.cliente:
        env_path = os.path.join(BASE_DIR, "clientes", args.cliente, ".env")
    else:
        env_path = os.path.join(BASE_DIR, ".env")

    values = {
        "META_PAGE_ACCESS_TOKEN": page_access_token,
        "META_PAGE_ID": page_id,
    }
    if ig_user_id:
        values["META_IG_USER_ID"] = ig_user_id

    _write_env_vars(env_path, values)
    print(f"\nListo. Guardé META_PAGE_ACCESS_TOKEN, META_PAGE_ID"
          f"{' y META_IG_USER_ID' if ig_user_id else ''} en {env_path}")
    if not ig_user_id:
        print(
            "No encontré una cuenta de Instagram vinculada a esta Página. Vincúlala en "
            "la configuración de la Página de Facebook y vuelve a correr este script "
            "para agregar META_IG_USER_ID."
        )


if __name__ == "__main__":
    main()
