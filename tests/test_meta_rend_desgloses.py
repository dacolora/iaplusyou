"""Desgloses de la copia de Meta (spec E2 §5): edad+género, ubicación, país y dispositivo, en dos ventanas, con un doble
de `graph.paginar` y sin red. La parte pura (`fila`) y la que llama a Meta y escribe (`copiar`)."""
import logging

import pytest

from meta_rendimiento import cuentas, datos, desgloses, graph

CLI, ACT = "hf", "act_1"

FILA = {"spend": "100.5", "impressions": "1000", "clicks": "30",
        "outbound_clicks": [{"action_type": "outbound_click", "value": "12"}],
        "actions": [{"action_type": "omni_purchase", "value": "3"}, {"action_type": "purchase", "value": "2"}],
        "action_values": [{"action_type": "purchase", "value": "250.5"}]}
CLAVE_DE = {"age,gender": {"age": "25-34", "gender": "female"},
            "publisher_platform,platform_position": {"publisher_platform": "facebook", "platform_position": "feed"},
            "country": {"country": "NO"}, "impression_device": {"impression_device": "iphone"}}


class FakePaginar:
    """Responde a cada consulta de desglose con una fila de ejemplo, o con lo que diga `filas`/`falla`."""

    def __init__(self, monkeypatch, filas=None, falla=None):
        self.llamadas = []
        self.filas = filas or {}      # {(preset, breakdowns): [filas de Meta]} (lo que falte: una fila de ejemplo)
        self.falla = falla or {}      # {(preset, breakdowns): excepción}
        monkeypatch.setattr(graph, "paginar", self.paginar)

    def paginar(self, edge, token, params=None, max_paginas=200, timeout=60, por_pagina=None):
        self.llamadas.append((edge, token, dict(params)))
        k = (params["date_preset"], params["breakdowns"])
        if k in self.falla:
            raise self.falla[k]
        return self.filas.get(k, [dict(FILA, **CLAVE_DE[params["breakdowns"]])])


@pytest.fixture()
def cuenta(base_temporal):
    cuentas.elegir(CLI, [{"id": ACT, "name": "HF", "currency": "SEK"}])
    return ACT


# ------------------------------------------------------------ constantes ---

def test_las_dimensiones_y_las_ventanas_son_las_del_spec():
    assert desgloses.DIMENSIONES == {"edad_genero": "age,gender", "ubicacion": "publisher_platform,platform_position",
                                     "pais": "country", "dispositivo": "impression_device"}
    assert desgloses.VENTANAS == (7, 30)
    # Lo que se pide es lo que la capa de datos sabe guardar.
    assert tuple(desgloses.DIMENSIONES) == datos.DIMENSIONES and desgloses.VENTANAS == datos.VENTANAS_DESGLOSE


# ------------------------------------------------------------ fila (pura) ---

def test_fila_une_los_valores_con_barra_en_el_orden_de_la_dimension():
    f = desgloses.fila(dict(FILA, age="25-34", gender="female"), "edad_genero")
    assert f == {"clave": "25-34|female", "gasto": 100.5, "impresiones": 1000, "clics": 30, "clics_salida": 12,
                 "compras": 2.0, "valor": 250.5}   # compras: el primer tipo presente de TIPOS_COMPRA, no la suma
    assert desgloses.fila(dict(FILA, platform_position="feed", publisher_platform="facebook"),
                          "ubicacion")["clave"] == "facebook|feed"
    assert desgloses.fila(dict(FILA, country="NO"), "pais")["clave"] == "NO"
    assert desgloses.fila(dict(FILA, impression_device="iphone"), "dispositivo")["clave"] == "iphone"


def test_fila_un_valor_que_falta_es_unknown_y_sin_ningun_valor_no_hay_clave():
    assert desgloses.fila(dict(FILA, age="18-24"), "edad_genero")["clave"] == "18-24|unknown"
    assert desgloses.fila(dict(FILA, age="unknown", gender=" "), "edad_genero")["clave"] == "unknown|unknown"
    # Una fila sin ningún valor de la dimensión no es un segmento: datos la ignora.
    assert desgloses.fila(dict(FILA), "pais")["clave"] is None


def test_fila_sin_clics_de_salida_usa_los_de_enlace_y_sin_datos_da_ceros():
    f = desgloses.fila({"country": "SE", "inline_link_clicks": "7", "spend": None, "clicks": "x"}, "pais")
    assert (f["clics_salida"], f["gasto"], f["clics"], f["compras"], f["valor"]) == (7, 0.0, 0, 0.0, 0.0)


def test_fila_de_una_dimension_desconocida_levanta():
    with pytest.raises(KeyError):
        desgloses.fila(dict(FILA, country="NO"), "pais_raro")


# ------------------------------------------------------------------ copiar ---

def test_copiar_pide_ocho_combinaciones_y_las_escribe(cuenta, monkeypatch):
    g = FakePaginar(monkeypatch)
    n = desgloses.copiar(CLI, ACT, "tok")
    assert n == 8 and len(g.llamadas) == 8
    pedidos = {(p["date_preset"], p["breakdowns"]) for _, _, p in g.llamadas}
    assert pedidos == {(f"last_{v}d", b) for v in (7, 30) for b in desgloses.DIMENSIONES.values()}
    for edge, token, p in g.llamadas:
        assert edge == f"{ACT}/insights" and token == "tok"
        assert p["level"] == "account" and p["limit"] == 500
        assert p["fields"] == "spend,impressions,clicks,outbound_clicks,inline_link_clicks,actions,action_values"
    for v in (7, 30):
        por = {(f["dimension"], f["clave"]): f for f in datos.desgloses(CLI, [ACT], v)}
        assert set(por) == {("edad_genero", "25-34|female"), ("ubicacion", "facebook|feed"), ("pais", "NO"),
                            ("dispositivo", "iphone")}
        assert por[("pais", "NO")]["gasto"] == 100.5 and por[("pais", "NO")]["compras"] == 2.0
        assert por[("pais", "NO")]["clics_salida"] == 12 and por[("pais", "NO")]["valor"] == 250.5


def test_copiar_reemplaza_la_combinacion_y_deja_vacia_la_que_ya_no_trae_filas(cuenta, monkeypatch):
    FakePaginar(monkeypatch)
    desgloses.copiar(CLI, ACT, "tok")
    FakePaginar(monkeypatch, filas={("last_30d", "country"): [dict(FILA, country="SE", spend="7")],
                                    ("last_7d", "country"): []})
    n = desgloses.copiar(CLI, ACT, "tok")
    assert n == 6 + 1       # las dos de país: 1 (30 días) + 0 (7 días); las otras seis combinaciones traen su fila
    assert [f["clave"] for f in datos.desgloses(CLI, [ACT], 30) if f["dimension"] == "pais"] == ["SE"]
    assert [f for f in datos.desgloses(CLI, [ACT], 7) if f["dimension"] == "pais"] == []


def test_copiar_un_limite_de_meta_sube_y_no_pide_mas(cuenta, monkeypatch):
    limite = graph.ErrorGraph("Meta pidió esperar", codigo=17)
    g = FakePaginar(monkeypatch, falla={("last_7d", "country"): limite})
    with pytest.raises(graph.ErrorGraph) as e:
        desgloses.copiar(CLI, ACT, "tok")
    assert e.value is limite and e.value.limite is True
    ultimo = g.llamadas[-1][2]
    assert (ultimo["date_preset"], ultimo["breakdowns"]) == ("last_7d", "country")   # nada después del límite


def test_copiar_un_uso_alto_de_la_api_tambien_sube(cuenta, monkeypatch):
    uso = graph.ErrorGraph("cerca del límite", limite=True, espera_min=30)
    FakePaginar(monkeypatch, falla={("last_7d", "age,gender"): uso})
    with pytest.raises(graph.ErrorGraph) as e:
        desgloses.copiar(CLI, ACT, "tok")
    assert e.value.limite is True and e.value.espera_min == 30


def test_copiar_otro_error_de_una_combinacion_se_anota_y_sigue_con_la_siguiente(cuenta, monkeypatch, caplog):
    FakePaginar(monkeypatch)
    desgloses.copiar(CLI, ACT, "tok")
    secreto = "tok-secreto-que-Meta-cito"
    g = FakePaginar(monkeypatch, falla={
        ("last_7d", "country"): graph.ErrorGraph(f"Meta respondió: {secreto}", codigo=100),
        ("last_30d", "impression_device"): ValueError(secreto)})
    with caplog.at_level(logging.WARNING, logger="creatv.meta_rendimiento.desgloses"):
        n = desgloses.copiar(CLI, ACT, "tok")
    assert len(g.llamadas) == 8 and n == 6       # las 8 se intentaron; escribió las 6 que respondieron
    # En el registro va el nombre del error y de qué combinación, nunca su texto (puede traer el token o la URL).
    texto = "\n".join(r.getMessage() for r in caplog.records)
    assert "ErrorGraph" in texto and "ValueError" in texto and "pais" in texto and "dispositivo" in texto
    assert "tok" not in texto
    # Las que fallaron conservan lo que ya tenían (no se borra lo bueno por un fallo pasajero).
    assert [f["clave"] for f in datos.desgloses(CLI, [ACT], 7) if f["dimension"] == "pais"] == ["NO"]
    assert [f["clave"] for f in datos.desgloses(CLI, [ACT], 30) if f["dimension"] == "dispositivo"] == ["iphone"]


def test_copiar_filtra_los_valores_ajenos_a_la_dimension_y_acepta_unknown(cuenta, monkeypatch):
    FakePaginar(monkeypatch, filas={("last_30d", "country"): [
        dict(FILA, country="NO", spend="10"), dict(FILA, country="unknown", spend="5"), dict(FILA, spend="99")]})
    desgloses.copiar(CLI, ACT, "tok")
    claves = sorted(f["clave"] for f in datos.desgloses(CLI, [ACT], 30) if f["dimension"] == "pais")
    assert claves == ["NO", "unknown"]      # la fila sin país no es un segmento
