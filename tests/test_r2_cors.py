"""La regla CORS del bucket: solo lectura (GET/HEAD) desde la plataforma y
el desarrollo local; se escribe con put_bucket_cors y nada más."""
import pytest

from storage import r2_cors


class S3Falso:
    def __init__(self, reglas=None, error=None):
        self.reglas, self.error, self.escrito = reglas, error, None

    def get_bucket_cors(self, Bucket):
        if self.error:
            raise self.error
        return {"CORSRules": self.reglas}

    def put_bucket_cors(self, Bucket, CORSConfiguration):
        self.escrito = (Bucket, CORSConfiguration)


def test_origenes_incluyen_la_plataforma_los_extra_y_los_locales(monkeypatch):
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.ejemplo.com/")
    monkeypatch.setenv("R2_CORS_EXTRA", "https://otro.ejemplo.com, ,https://app.ejemplo.com")
    o = r2_cors.origenes()
    assert o[0] == "https://app.ejemplo.com"
    assert "https://otro.ejemplo.com" in o and o.count("https://app.ejemplo.com") == 1
    assert "http://127.0.0.1:5050" in o and "http://localhost:8765" in o


def test_regla_es_solo_lectura():
    r = r2_cors.regla(["https://app.ejemplo.com"])["CORSRules"][0]
    assert r["AllowedMethods"] == ["GET", "HEAD"]
    assert r["AllowedOrigins"] == ["https://app.ejemplo.com"]
    assert "Content-Range" in r["ExposeHeaders"]


def test_aplicar_escribe_en_el_bucket_del_entorno(monkeypatch):
    monkeypatch.setenv("R2_BUCKET_NAME", "cubeta")
    monkeypatch.setenv("PLATAFORMA_URL", "https://app.ejemplo.com")
    s3 = S3Falso()
    reglas = r2_cors.aplicar(s3)
    assert s3.escrito[0] == "cubeta"
    assert s3.escrito[1]["CORSRules"] == reglas
    assert reglas[0]["AllowedOrigins"][0] == "https://app.ejemplo.com"


def test_actual_sin_regla_es_lista_vacia(monkeypatch):
    monkeypatch.setenv("R2_BUCKET_NAME", "cubeta")
    assert r2_cors.actual(S3Falso(error=RuntimeError("NoSuchCORSConfiguration: nada"))) == []
    with pytest.raises(RuntimeError):
        r2_cors.actual(S3Falso(error=RuntimeError("AccessDenied")))
