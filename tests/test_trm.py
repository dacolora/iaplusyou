"""TRM oficial (spec planes 2026-10-09 §6): datos.gov.co, caché de 6 h en
`kv` y respaldo de hasta 3 días. Nunca llama a la red."""
import datetime as dt
import json

import pytest
import requests as requests_real

URL = "https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=1&$order=vigenciadesde%20DESC"
HOY = dt.date(2026, 10, 9)
T0 = 1_791_500_000.0


class _Respuesta:
    def __init__(self, status_code=200, datos=None, texto=None):
        self.status_code = status_code
        self._datos = datos
        self._texto = texto

    def json(self):
        if self._texto is not None:
            raise ValueError("no es JSON")
        return self._datos


def _fila(valor="3218.75", desde="2026-10-09", hasta="2026-10-09"):
    return [{"valor": valor, "unidad": "COP", "vigenciadesde": f"{desde}T00:00:00.000",
             "vigenciahasta": f"{hasta}T00:00:00.000"}]


@pytest.fixture()
def trm(base_temporal, monkeypatch):
    from cobros import trm as mod
    reloj = {"t": T0, "hoy": HOY}
    monkeypatch.setattr(mod, "_ahora", lambda: reloj["t"])
    monkeypatch.setattr(mod, "_hoy", lambda: reloj["hoy"])
    llamadas = []
    respuesta = {"r": _Respuesta(200, _fila())}

    def get(url, **k):
        llamadas.append((url, k))
        r = respuesta["r"]
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(mod.requests, "get", get)
    monkeypatch.setattr(mod.requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("sin post")))
    mod.reloj, mod.llamadas, mod.respuesta = reloj, llamadas, respuesta
    return mod


def _guardado(db):
    import sqlalchemy as sa
    with db.conectar() as con:
        crudo = con.execute(sa.select(db.kv.c.valor).where(db.kv.c.clave == "cobros:trm")).scalar()
    return json.loads(crudo) if crudo else None


def test_lee_la_tasa_del_host_fijo(trm, base_temporal):
    assert trm.actual() == 3218.75
    (url, k), = trm.llamadas
    assert url == URL
    assert k["timeout"] == 10
    assert k["allow_redirects"] is False
    g = _guardado(base_temporal)
    assert g["valor"] == 3218.75 and g["leida_en"] == T0
    assert g["vigencia_hasta"].startswith("2026-10-09")


def test_usa_la_cache_por_seis_horas(trm):
    assert trm.actual() == 3218.75
    trm.respuesta["r"] = _Respuesta(200, _fila("3300.00"))
    trm.reloj["t"] = T0 + 6 * 3600 - 1
    assert trm.actual() == 3218.75
    assert len(trm.llamadas) == 1
    trm.reloj["t"] = T0 + 6 * 3600 + 1
    assert trm.actual() == 3300.0
    assert len(trm.llamadas) == 2


@pytest.mark.parametrize("falla", [
    requests_real.ConnectionError("x"), requests_real.Timeout("x"),
    _Respuesta(500, texto="boom"), _Respuesta(429, {}), _Respuesta(301, {}),
    _Respuesta(200, texto="<html>"), _Respuesta(200, []), _Respuesta(200, [{"valor": "abc"}]),
    _Respuesta(200, [{"unidad": "COP"}]), _Respuesta(200, {"valor": "3218.75"}),
    _Respuesta(200, _fila("0")), _Respuesta(200, _fila("-3218")), _Respuesta(200, _fila("32187500")),
    _Respuesta(200, _fila("nan")), _Respuesta(200, _fila("inf")),
])
def test_si_falla_usa_la_guardada_de_hasta_tres_dias(trm, falla):
    assert trm.actual() == 3218.75
    trm.respuesta["r"] = falla
    trm.reloj["t"] = T0 + 3 * 86400 - 60
    trm.reloj["hoy"] = HOY + dt.timedelta(days=2)
    assert trm.actual() == 3218.75


def test_si_falla_y_la_guardada_es_vieja_no_hay_tasa(trm):
    assert trm.actual() == 3218.75
    trm.respuesta["r"] = requests_real.ConnectionError("x")
    trm.reloj["t"] = T0 + 3 * 86400 + 60
    trm.reloj["hoy"] = HOY + dt.timedelta(days=3)
    with pytest.raises(trm.SinTasa) as e:
        trm.actual()
    assert "tasa de cambio" in str(e.value)


def test_sin_red_y_sin_guardada_no_hay_tasa(trm):
    trm.respuesta["r"] = requests_real.ConnectionError("x")
    with pytest.raises(trm.SinTasa):
        trm.actual()


def test_una_tasa_publicada_hace_mas_de_tres_dias_no_sirve(trm):
    """Si datos.gov.co deja de actualizarse, su última fila no es «la del día»."""
    trm.respuesta["r"] = _Respuesta(200, _fila(desde="2026-10-01", hasta="2026-10-05"))
    with pytest.raises(trm.SinTasa):
        trm.actual()


def test_la_tasa_de_fin_de_semana_sirve_mientras_esta_vigente(trm):
    trm.reloj["hoy"] = dt.date(2026, 10, 12)
    trm.respuesta["r"] = _Respuesta(200, _fila("3200.10", desde="2026-10-10", hasta="2026-10-13"))
    assert trm.actual() == 3200.10


def test_una_guardada_ilegible_se_ignora(trm, base_temporal):
    with base_temporal.conectar() as con:
        con.execute(base_temporal.kv.insert().values(clave="cobros:trm", valor="{no es json",
                                                     actualizado_en=base_temporal.ahora()))
    assert trm.actual() == 3218.75
    assert _guardado(base_temporal)["valor"] == 3218.75


def test_dos_lecturas_seguidas_dejan_una_sola_fila(trm, base_temporal):
    import sqlalchemy as sa
    trm.actual()
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3250.5"))
    assert trm.actual() == 3250.5
    with base_temporal.conectar() as con:
        n = con.execute(sa.select(sa.func.count()).select_from(base_temporal.kv)
                        .where(base_temporal.kv.c.clave == "cobros:trm")).scalar()
    assert n == 1


def test_una_guardada_fuera_de_rango_no_sirve_de_respaldo(trm, base_temporal):
    with base_temporal.conectar() as con:
        con.execute(base_temporal.kv.insert().values(
            clave="cobros:trm", actualizado_en=base_temporal.ahora(),
            valor=json.dumps({"valor": 0.5, "leida_en": T0, "vigencia_hasta": "2026-10-09T00:00:00.000"})))
    trm.respuesta["r"] = requests_real.ConnectionError("x")
    with pytest.raises(trm.SinTasa):
        trm.actual()
