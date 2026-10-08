"""Anillos, tendencia y frases (spec tarjetas §4). Todo puro."""
from tests.test_triple_whale_evaluacion import REGLAS, anuncio
from triple_whale import evaluacion as ev


def _por_id(r):
    return {a["ad_id"]: a for a in r["anuncios"]}


def test_percentil_por_canal_con_empates_y_sin_contarse_a_si_mismo():
    # CTR 1, 2, 2, 3 % en Meta; en Snapchat uno con CTR altísimo que no debe contar para Meta.
    lista = [anuncio("a", clics=100), anuncio("b", clics=200), anuncio("c", clics=200), anuncio("d", clics=300),
             anuncio("s1", clics=900, canal="snapchat-ads")]
    a = _por_id(ev.evaluar(lista, reglas=REGLAS))
    assert a["a"]["anillos"]["clic"]["pct"] == 0                 # 0 menores de 3
    assert a["b"]["anillos"]["clic"]["pct"] == 50                # (1 menor + 0,5 × 1 igual) / 3
    assert a["d"]["anillos"]["clic"]["pct"] == 100
    assert a["d"]["anillos"]["clic"]["nivel"] == "alto" and a["a"]["anillos"]["clic"]["nivel"] == "bajo"
    assert a["b"]["anillos"]["clic"]["nivel"] == "medio"
    # Snapchat queda solo en su canal: no hay con quién comparar.
    assert a["s1"]["anillos"]["clic"] == {"pct": None, "valor": 9.0, "nivel": None, "vacio": "pocas_comparables"}


def test_imagen_sin_gancho_ni_retencion_y_pocos_datos():
    lista = [anuncio("v1"), anuncio("v2"), anuncio("v3"),
             anuncio("img", vistas_3s=0, thruplays=0), anuncio("chico", impresiones=200, clics=4)]
    a = _por_id(ev.evaluar(lista, reglas=REGLAS))
    assert a["img"]["anillos"]["gancho"]["vacio"] == "sin_video" and a["img"]["anillos"]["retencion"]["pct"] is None
    assert a["img"]["anillos"]["clic"]["pct"] is not None
    assert a["chico"]["anillos"]["clic"]["vacio"] == "pocos_datos"
    assert set(a["v1"]["anillos"]) == set(ev.ANILLOS)


def test_compra_solo_con_ventas_en_la_cuenta_y_clics_suficientes():
    sin_ventas = _por_id(ev.evaluar([anuncio("1"), anuncio("2"), anuncio("3")], reglas=REGLAS))
    assert sin_ventas["1"]["anillos"]["compra"]["vacio"] == "sin_ventas"
    con = _por_id(ev.evaluar([anuncio("1", pedidos=3, ingresos=300), anuncio("2", pedidos=1, ingresos=90),
                              anuncio("3", pedidos=2, ingresos=200), anuncio("pocos", clics=20, pedidos=1, ingresos=90)],
                             reglas=REGLAS))
    assert con["1"]["anillos"]["compra"]["pct"] == 100 and con["2"]["anillos"]["compra"]["pct"] == 0
    assert con["pocos"]["anillos"]["compra"]["vacio"] == "pocos_clics"


def test_medianas_por_canal_en_el_diagnostico():
    # En Meta el CTR típico es 1,5 %; en Snapchat 0,3 %. Un Snapchat de 0,3 % no es «pocos clics».
    lista = [anuncio(f"m{i}", clics=150) for i in range(4)]
    lista += [anuncio(f"s{i}", clics=30, canal="snapchat-ads") for i in range(4)]
    r = ev.evaluar(lista, reglas=REGLAS)
    assert set(r["benchmarks_canal"]) == {"facebook-ads", "snapchat-ads"}
    assert r["benchmarks_canal"]["snapchat-ads"]["ctr"] == 0.3
    assert "sin_clic" not in _por_id(r)["s0"]["problemas"]


def test_canal_sin_comparables_cae_a_las_medianas_de_la_cuenta():
    lista = [anuncio(f"m{i}", clics=150) for i in range(4)] + [anuncio("s0", clics=30, canal="snapchat-ads")]
    assert "sin_clic" in _por_id(ev.evaluar(lista, reglas=REGLAS))["s0"]["problemas"]


def _m(**kw):
    base = {"gasto": 100.0, "impresiones": 5000, "pedidos": 4, "roas": 2.0, "ctr": 1.0}
    base.update(kw)
    return base


def test_tendencia():
    assert ev.tendencia(_m(), _m(), REGLAS, fatiga=True) == "cansando"
    assert ev.tendencia(_m(roas=2.5), _m(roas=2.0), REGLAS) == "mejorando"
    assert ev.tendencia(_m(ctr=1.3), _m(ctr=1.0), REGLAS) == "mejorando"
    assert ev.tendencia(None, _m(), REGLAS) == "sin_gasto"
    assert ev.tendencia(_m(gasto=0.0), _m(), REGLAS) == "sin_gasto"
    assert ev.tendencia(_m(), _m(), REGLAS) == "estable"
    assert ev.tendencia(_m(impresiones=100), _m(), REGLAS) is None
    assert ev.tendencia(None, None, REGLAS) is None


def test_evaluar_deja_la_tendencia_de_cada_anuncio():
    total = [anuncio("1"), anuncio("2"), anuncio("3")]
    previos = [anuncio("1", impresiones=5000), anuncio("2", impresiones=5000)]
    recientes = [anuncio("1", impresiones=5000)]
    a = _por_id(ev.evaluar(total, recientes, previos, REGLAS))
    assert a["1"]["tendencia"] == "estable" and a["2"]["tendencia"] == "sin_gasto" and a["3"]["tendencia"] is None


def test_frases_y_textos_cubren_todo():
    assert set(ev.FRASES_VEREDICTO) == set(ev.VEREDICTOS)
    assert set(ev.TENDENCIAS) == {"cansando", "mejorando", "sin_gasto", "estable"}
    assert set(ev.VACIOS_ANILLO) == {"sin_video", "pocos_datos", "pocas_comparables", "sin_ventas", "pocos_clics"}
