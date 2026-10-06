"""
Autorización OAuth de una sola vez para TikTok.

Antes de correr esto necesitas (ver SETUP.md para el paso a paso):
  1. Una app en developers.tiktok.com con el producto "Content Posting API" agregado.
  2. TIKTOK_CLIENT_KEY y TIKTOK_CLIENT_SECRET en tu .env.
  3. La URI de redirección http://localhost:8766/callback agregada en la
     configuración de la app.

Uso:
    python auth/auth_tiktok.py                     # cuenta propia (uso de un solo cliente)
    python auth/auth_tiktok.py --cliente empresa_a  # autoriza la cuenta de esa empresa

IMPORTANTE: mientras tu app esté en modo sandbox/sin auditar, solo podrás publicar
en la(s) cuenta(s) de TikTok que agregues como "target users" de prueba en el
panel de developers.tiktok.com, y en modo privado (Solo yo). Para publicar público
en cualquier cuenta hace falta pasar la auditoría de Content Posting API.
"""
import argparse
import os
import json
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from dotenv import load_dotenv

load_dotenv()

REDIRECT_URI = "http://localhost:8766/callback"
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")

_captured = {}


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            _captured["code"] = params["code"][0]
            _captured["state"] = (params.get("state") or [""])[0]
            body = b"Autorizado. Ya puedes cerrar esta pestana y volver a la terminal."
        else:
            body = b"No recibi un codigo de autorizacion. Revisa la terminal."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def _wait_for_code(estado):
    server = HTTPServer(("localhost", 8766), _CallbackHandler)
    while "code" not in _captured:
        server.handle_request()
    server.server_close()
    if not secrets.compare_digest((_captured.get("state") or "").encode(), estado.encode()):
        raise RuntimeError("La respuesta de TikTok no trae el `state` de esta autorización; vuelve a correr el script.")
    return _captured["code"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cliente", help="Nombre de carpeta bajo clientes/, si aplica")
    args = parser.parse_args()

    client_key = os.environ.get("TIKTOK_CLIENT_KEY")
    client_secret = os.environ.get("TIKTOK_CLIENT_SECRET")
    if not client_key or not client_secret:
        raise RuntimeError("Faltan TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET en tu .env")

    # `state` aleatorio y comprobado al volver: mientras esto espera, cualquier
    # página abierta en el navegador podría llamar a localhost:8766/callback con
    # el código de OTRA cuenta de TikTok y quedaría vinculada a este proyecto.
    estado = secrets.token_urlsafe(24)
    auth_url = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(
        {
            "client_key": client_key,
            "scope": "video.publish,user.info.basic",
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "state": estado,
        }
    )
    print("Abriendo el navegador para autorizar con TikTok...")
    print(f"Si no se abre solo, visita:\n{auth_url}\n")
    webbrowser.open(auth_url)

    code = _wait_for_code(estado)

    token_resp = requests.post(
        "https://open.tiktokapis.com/v2/oauth/token/",
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    token_resp.raise_for_status()
    token_data = token_resp.json()

    if args.cliente:
        client_dir = os.path.join(BASE_DIR, "clientes", args.cliente)
        os.makedirs(client_dir, exist_ok=True)
        token_path = os.path.join(client_dir, "token_tiktok.json")
    else:
        token_path = os.path.join(BASE_DIR, "token_tiktok.json")

    # 0600: el token da acceso a la cuenta; nadie más en la máquina debe leerlo.
    fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(token_data, f)
    os.chmod(token_path, 0o600)

    print(f"Listo. Autorización guardada en {token_path}")


if __name__ == "__main__":
    main()
