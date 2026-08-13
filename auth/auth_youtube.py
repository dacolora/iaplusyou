"""
Autorización OAuth de una sola vez para YouTube.

Antes de correr esto necesitas:
  1. Un proyecto en Google Cloud Console con la "YouTube Data API v3" habilitada.
  2. Una pantalla de consentimiento OAuth configurada (modo "Externo" está bien).
  3. Un cliente OAuth tipo "App de escritorio" (Desktop app), descargado como JSON.
     Guarda ese archivo en esta carpeta como: client_secret_youtube.json

Ver SETUP.md para el paso a paso completo.

Uso:
    python auth/auth_youtube.py                     # cuenta propia (uso de un solo cliente)
    python auth/auth_youtube.py --cliente empresa_a  # autoriza el canal de esa empresa

Esto abre el navegador para que la cuenta correspondiente inicie sesión y autorice la
app. El cliente OAuth (client_secret_youtube.json) es siempre el mismo, tuyo; lo que
cambia por empresa es el canal que se autoriza y por lo tanto el token resultante.
"""
import argparse
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
CLIENT_SECRET_PATH = os.path.join(BASE_DIR, "client_secret_youtube.json")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cliente", help="Nombre de carpeta bajo clientes/, si aplica")
    args = parser.parse_args()

    if not os.path.exists(CLIENT_SECRET_PATH):
        raise RuntimeError(
            f"No encontré {CLIENT_SECRET_PATH}. Descarga el JSON de tu cliente OAuth "
            "de escritorio desde Google Cloud Console y guárdalo con ese nombre. "
            "Ver SETUP.md."
        )

    if args.cliente:
        client_dir = os.path.join(BASE_DIR, "clientes", args.cliente)
        os.makedirs(client_dir, exist_ok=True)
        token_path = os.path.join(client_dir, "token_youtube.json")
    else:
        token_path = os.path.join(BASE_DIR, "token_youtube.json")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print(f"Listo. Autorización guardada en {token_path}")


if __name__ == "__main__":
    main()
