"""CORS del bucket de R2 (spec editor §3, capa 3): la vista previa dibuja los
videos en un <canvas> y mezcla el audio con Web Audio. Sin CORS el navegador
entrega silencio de un medio de otro origen y no deja leer el lienzo (la
capa 5 compara esa captura con el render). La regla es de solo lectura
(GET/HEAD) y se aplica a mano, una vez, con el OK del dueño del bucket:

    venv/bin/python3 -m storage.r2_cors            # muestra la regla actual y la nueva
    venv/bin/python3 -m storage.r2_cors --aplicar  # la escribe

Orígenes: PLATAFORMA_URL, los de R2_CORS_EXTRA (separados por coma) y los
del desarrollo local (dashboard en :5050, servidor de prueba en :8765)."""
import os
import sys

ORIGENES_LOCALES = ("http://127.0.0.1:5050", "http://localhost:5050",
                    "http://127.0.0.1:8765", "http://localhost:8765")


def origenes():
    out = []
    base = (os.environ.get("PLATAFORMA_URL") or "").strip().rstrip("/")
    if base:
        out.append(base)
    for o in (os.environ.get("R2_CORS_EXTRA") or "").split(","):
        o = o.strip().rstrip("/")
        if o:
            out.append(o)
    out += ORIGENES_LOCALES
    return list(dict.fromkeys(out))


def regla(origenes_):
    return {"CORSRules": [{
        "AllowedOrigins": list(origenes_),
        "AllowedMethods": ["GET", "HEAD"],
        "AllowedHeaders": ["*"],
        "ExposeHeaders": ["Content-Length", "Content-Range", "Accept-Ranges", "ETag"],
        "MaxAgeSeconds": 3600,
    }]}


def _s3():
    from storage.r2_uploader import _client
    return _client()


def actual(s3=None):
    s3 = s3 or _s3()
    try:
        return s3.get_bucket_cors(Bucket=os.environ["R2_BUCKET_NAME"]).get("CORSRules") or []
    except Exception as e:
        if "NoSuchCORSConfiguration" in str(e):
            return []
        raise


def aplicar(s3=None):
    s3 = s3 or _s3()
    conf = regla(origenes())
    s3.put_bucket_cors(Bucket=os.environ["R2_BUCKET_NAME"], CORSConfiguration=conf)
    return conf["CORSRules"]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
    print("Regla actual:", actual())
    print("Regla nueva: ", regla(origenes())["CORSRules"])
    if "--aplicar" in sys.argv:
        print("Aplicada:    ", aplicar())
