"""
Wizard de configuración de Meta Ads — un cliente a la vez, mismo espíritu
que auth/auth_meta.py pero para permisos de anuncios pagos (Marketing API)
en vez de posting orgánico.

Uso:
    python3 auth/auth_meta_ads.py                    # modo un solo cliente (raíz)
    python3 auth/auth_meta_ads.py --cliente empresa_a  # guarda en clientes/empresa_a/.env

Guarda META_AD_ACCOUNT_ID (y confirma que META_PAGE_ACCESS_TOKEN ya tiene el
scope ads_management) en el .env del cliente correspondiente — nunca en el
.env raíz, para que cada cliente futuro corra este mismo script con su
propio nombre y quede aislado de los demás (ver
docs/superpowers/specs/2026-09-05-meta-ads-marketing-api-design.md,
"Fase 0").
"""
import argparse
import os
import sys

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _client_env_path(cliente):
    if cliente:
        carpeta = os.path.join(BASE_DIR, "clientes", cliente)
        os.makedirs(carpeta, exist_ok=True)
        return os.path.join(carpeta, ".env")
    return os.path.join(BASE_DIR, ".env")


def _append_env(ruta, clave, valor):
    lineas = []
    if os.path.exists(ruta):
        with open(ruta) as f:
            lineas = f.readlines()
    lineas = [l for l in lineas if not l.startswith(f"{clave}=")]
    lineas.append(f"{clave}={valor}\n")
    with open(ruta, "w") as f:
        f.writelines(lineas)


def main():
    parser = argparse.ArgumentParser(description="Wizard de configuración de Meta Ads (Marketing API), un cliente a la vez.")
    parser.add_argument("--cliente", default=None, help="Nombre del cliente (carpeta en clientes/). Sin esto, usa el .env de la raíz.")
    args = parser.parse_args()

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    client_env = _client_env_path(args.cliente) if args.cliente else None
    if client_env and os.path.exists(client_env):
        load_dotenv(client_env, override=True)

    print("=== Wizard de Meta Ads ===\n")

    print("Paso 1 — Business Manager")
    print("  ¿Ya tienes un Business Manager? (business.facebook.com)")
    print("  Si no: entra a business.facebook.com/overview, botón 'Crear cuenta',")
    print("  sigue el formulario (nombre del negocio, tu nombre, correo).")
    input("  Presiona Enter cuando tengas un Business Manager listo... ")

    print("\nPaso 2 — Ad Account")
    print("  Dentro del Business Manager: Configuración del negocio > Cuentas >")
    print("  Cuentas publicitarias > Agregar > Crear una cuenta publicitaria nueva.")
    print("  Agrega un método de pago (Configuración de pagos) — sin esto Meta")
    print("  no deja activar ninguna campaña, aunque sí deja crearlas en PAUSED.")
    ad_account_id = input("  Pega el ID de la cuenta publicitaria (el número, sin 'act_'): ").strip()

    print("\nPaso 3 — Permiso ads_management")
    print("  En developers.facebook.com, tu app (la misma que ya usa")
    print("  META_PAGE_ACCESS_TOKEN) necesita el permiso 'ads_management' agregado.")
    print("  Esto requiere App Review + Business Verification de Meta — puede")
    print("  tardar varios días. Ve a tu app > Revisión de la app > Permisos y")
    print("  características > busca 'ads_management' > Solicitar.")
    input("  Presiona Enter cuando Meta haya APROBADO el permiso (no antes)... ")

    if not os.environ.get("META_PAGE_ACCESS_TOKEN"):
        print("\n  Falta META_PAGE_ACCESS_TOKEN en tu .env — corre primero")
        print("  auth/auth_meta.py (el de posting orgánico), este wizard reusa ese token.")
        sys.exit(1)

    print("\nPaso 4 — Validar acceso real")
    os.environ["META_AD_ACCOUNT_ID"] = ad_account_id
    from meta_ads import auth as meta_auth  # import tardío: recién ahora existe la env var

    try:
        resultado = meta_auth.llamar("GET", f"act_{ad_account_id}/campaigns", params={"limit": 1})
        print(f"  Acceso confirmado — Meta respondió: {resultado}")
    except Exception as e:
        print(f"\n  La validación falló: {e}")
        print("  Revisa que el permiso ads_management ya esté aprobado y que el ID")
        print("  de la cuenta publicitaria sea correcto, y vuelve a correr este script.")
        sys.exit(1)

    ruta = client_env or os.path.join(BASE_DIR, ".env")
    _append_env(ruta, "META_AD_ACCOUNT_ID", ad_account_id)
    print(f"\n  META_AD_ACCOUNT_ID guardado en {ruta}")
    print("  Listo — ya puedes publicar anuncios desde la pestaña Publicidad.")


if __name__ == "__main__":
    main()
