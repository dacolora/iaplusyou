"""TRM oficial (spec planes 2026-10-09 §6): datos.gov.co, caché de 6 h en
`kv` y respaldo de hasta 3 días. Nunca llama a la red."""
import datetime as dt
import json

import pytest
import requests as requests_real

URL = ("https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=1&$order=vigenciadesde%20DESC"
       "&$where=vigenciadesde%20%3C%3D%20%272026-10-09T00%3A00%3A00%27")
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
    from cobros import avisos
    admin = []
    monkeypatch.setattr(avisos, "admin", lambda tipo, asunto, cuerpo, cliente="": admin.append((tipo, cuerpo())) or 1)
    mod.reloj, mod.llamadas, mod.respuesta, mod.admin = reloj, llamadas, respuesta, admin
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


def test_una_tasa_de_un_dia_futuro_no_sirve(trm):
    """Aunque el `$where` ya la filtra, una fila de mañana no es la TRM de hoy."""
    trm.respuesta["r"] = _Respuesta(200, _fila("3300.00", desde="2026-10-10", hasta="2026-10-10"))
    with pytest.raises(trm.SinTasa):
        trm.actual()


def test_no_poder_guardar_no_pierde_la_tasa_leida(trm, monkeypatch):
    def falla(*a, **k):
        raise RuntimeError("database is locked")
    monkeypatch.setattr(trm, "_guardar", falla)
    assert trm.actual() == 3218.75



# --- banda (revisión final 2026-10-10) ------------------------------------------------------

@pytest.mark.parametrize("valor", ["2499.99", "7000.01", "14800"])
def test_una_tasa_fuera_de_2500_7000_no_sirve_y_avisa_al_admin_una_vez_por_dia(trm, valor):
    trm.respuesta["r"] = _Respuesta(200, _fila(valor))
    with pytest.raises(trm.SinTasa):
        trm.actual()
    with pytest.raises(trm.SinTasa):
        trm.actual()
    assert [a[0] for a in trm.admin] == ["trm_sin_tasa"]          # una vez por día
    trm.reloj["hoy"] = HOY + dt.timedelta(days=1)
    with pytest.raises(trm.SinTasa):
        trm.actual()
    assert len(trm.admin) == 2


def test_un_salto_de_mas_de_8_por_ciento_frena_y_no_usa_ninguna(trm, base_temporal):
    assert trm.actual() == 3218.75
    trm.reloj["t"] = T0 + 7 * 3600                                 # pasó la caché
    trm.respuesta["r"] = _Respuesta(200, _fila("3500.00"))          # +8,7 %
    with pytest.raises(trm.SinTasa):
        trm.actual()
    assert _guardado(base_temporal)["valor"] == 3218.75            # la mala no se guarda
    assert [a[0] for a in trm.admin] == ["trm_sin_tasa"] and "3500" in trm.admin[0][1]
    trm.respuesta["r"] = _Respuesta(200, _fila("2950.00"))          # −8,3 %
    with pytest.raises(trm.SinTasa):
        trm.actual()


def test_dentro_del_8_por_ciento_se_usa(trm):
    assert trm.actual() == 3218.75
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3470.00"))          # +7,8 %
    assert trm.actual() == 3470.0 and trm.admin == []


def test_con_la_guardada_de_mas_de_tres_dias_un_salto_sigue_frenando(trm, base_temporal):
    """N3: pasados 3 días un salto de más de 8 % sigue sin aceptarse solo."""
    assert trm.actual() == 3218.75
    trm.reloj["t"] = T0 + 10 * 86400
    trm.reloj["hoy"] = HOY + dt.timedelta(days=10)
    trm.respuesta["r"] = _Respuesta(200, _fila("3600.00", desde="2026-10-19", hasta="2026-10-19"))
    with pytest.raises(trm.SinTasa):
        trm.actual()
    r = trm.rechazada()
    assert r["valor"] == 3600.0 and r["anterior"] == 3218.75
    assert _guardado(base_temporal)["valor"] == 3218.75


def test_la_rechazada_no_se_vuelve_a_pedir_en_una_hora(trm):
    assert trm.actual() == 3218.75
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3600.00"))
    with pytest.raises(trm.SinTasa):
        trm.actual()
    n = len(trm.llamadas)
    trm.reloj["t"] += 3599
    with pytest.raises(trm.SinTasa):
        trm.actual()
    assert len(trm.llamadas) == n                                  # dentro de la hora: no pide
    trm.reloj["t"] += 2
    with pytest.raises(trm.SinTasa):
        trm.actual()
    assert len(trm.llamadas) == n + 1


def test_el_dia_queda_avisado_solo_si_el_correo_salio(trm, monkeypatch):
    from cobros import avisos
    salidos = []
    monkeypatch.setattr(avisos, "admin", lambda tipo, a, c, cliente="": salidos.append(tipo) or 0)   # no salió
    trm.respuesta["r"] = _Respuesta(200, _fila("2400"))
    for _ in range(2):
        with pytest.raises(trm.SinTasa):
            trm.actual()
    assert salidos == ["trm_sin_tasa", "trm_sin_tasa"]             # se reintenta
    monkeypatch.setattr(avisos, "admin", lambda tipo, a, c, cliente="": salidos.append(tipo) or 1)   # salió
    for _ in range(2):
        with pytest.raises(trm.SinTasa):
            trm.actual()
    assert len(salidos) == 3                                        # una vez y ya, hasta mañana


def test_el_admin_acepta_la_tasa_rechazada(trm, base_temporal):
    assert trm.actual() == 3218.75
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3600.00"))
    with pytest.raises(trm.SinTasa):
        trm.actual()
    with pytest.raises(ValueError):
        trm.aceptar("3700", "admin")                                # solo la que se mostró
    assert trm.aceptar("3600.0", "admin") == 3600.0
    assert trm.rechazada() is None and trm.actual() == 3600.0
    with pytest.raises(ValueError):
        trm.aceptar("3600.0", "admin")                              # ya no hay nada que aceptar


def test_si_la_de_hoy_vuelve_a_la_banda_se_borra_la_rechazada(trm):
    assert trm.actual() == 3218.75
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3600.00"))
    with pytest.raises(trm.SinTasa):
        trm.actual()
    trm.reloj["t"] += 3601
    trm.respuesta["r"] = _Respuesta(200, _fila("3250.00"))
    assert trm.actual() == 3250.0 and trm.rechazada() is None



def test_con_una_rechazada_pendiente_y_datos_gov_caido_no_se_usa_la_vieja(trm):
    """R2: pasada la hora de la rechazada, si datos.gov.co no responde, la aceptada vieja no vale: sin cobro
    hasta que el admin acepte la de hoy o una lectura nueva pase la banda."""
    assert trm.actual() == 3218.75
    trm.reloj["t"] = T0 + 7 * 3600
    trm.respuesta["r"] = _Respuesta(200, _fila("3600.00"))
    with pytest.raises(trm.SinTasa):
        trm.actual()
    trm.reloj["t"] += 3601
    trm.respuesta["r"] = requests_real.ConnectionError("caído")
    with pytest.raises(trm.SinTasa):
        trm.actual()
    assert trm.rechazada()["valor"] == 3600.0
