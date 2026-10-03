import pytest
import cola


@pytest.mark.parametrize('texto', [
    'access_token: valor_ficticio',  # llave-de-prueba
    '{"access_token":"valor_ficticio","ok":1}',  # llave-de-prueba
    "{'upload_token': 'valor_ficticio'}",  # llave-de-prueba
    'TOKEN = valor_ficticio&ok=1',  # llave-de-prueba
])
def test_redacta_formatos_de_error(texto):
    assert 'valor_ficticio' not in cola.sin_token(texto)
    assert '***' in cola.sin_token(texto)


@pytest.mark.parametrize('texto, oculto', [
    ('?access_token=valor_ficticio&after=Y', 'valor_ficticio'),  # llave-de-prueba
    ('key=AIzaValorFicticio', 'AIzaValorFicticio'),  # llave-de-prueba
    ('upload_token=valor_ficticio)', 'valor_ficticio'),  # llave-de-prueba
    ('token=abc,def', 'abc,def'),  # llave-de-prueba
    ('token=a}SECRETO', 'SECRETO'),  # llave-de-prueba
    ('page_access_token=valor_ficticio', 'valor_ficticio'),  # llave-de-prueba
    ('\\"access_token\\":\\"valor_ficticio\\"', 'valor_ficticio'),  # llave-de-prueba
])
def test_tapa_lo_que_la_version_vieja_tapaba_y_mas(texto, oculto):
    """Auditoría del lote 3 (2026-10-03): ninguna forma que la expresión vieja tapaba
    queda a la vista (coma y llave incluidas), y la forma JSON escapada también."""
    assert oculto not in cola.sin_token(texto)


def test_no_cruza_saltos_de_linea_ni_rompe_el_json_del_error():
    assert cola.sin_token('invalid token:\nlinea siguiente') == 'invalid token:\nlinea siguiente'
    import meta_errores
    crudo = 'Meta Ads (x) respondió 400: {"error":{"message":"Missing key: \\"adset_id\\" in params","code":100}}'
    limpio = cola.sin_token(crudo)
    assert meta_errores._cadena(limpio, "message") == 'Missing key: "***" in params'


def test_el_plazo_corre_desde_que_se_tiene_el_candado(monkeypatch):
    """Esperar el candado de Meta (p. ej. una subida de video) no gasta el plazo."""
    import time
    import lanzador
    import meta_detalle as md
    vistos = []
    real = lanzador._con_credenciales

    def tarda_en_dar_el_candado(cliente, fn):
        time.sleep(0.3)
        vistos.append(md._PLAZO.get() is None)
        return fn({})

    monkeypatch.setattr(md, "PLAZO_S", 0.2)
    monkeypatch.setattr(lanzador, "_con_credenciales", tarda_en_dar_el_candado)
    llamadas = []
    monkeypatch.setattr(md, "pedir_diario", lambda *a: llamadas.append("diario") or [])
    monkeypatch.setattr(md, "pedir_desglose", lambda *a: llamadas.append("desglose") or [])
    monkeypatch.setattr(md, "pedir_rankings", lambda *a: llamadas.append("rankings") or [])
    ex = {"meta_campaign_id": "cmp", "creado_en": "2026-09-01T00:00:00", "piezas": [{"id": 1, "meta_ad_id": "ad"}], "extra": {}}
    monkeypatch.setattr(md.experimentos, "obtener", lambda c, e: ex)
    monkeypatch.setattr(md.experimentos, "actualizar_extra", lambda *a, **k: None)
    monkeypatch.setattr(md, "desde_para", lambda *a: "2026-09-01")
    r = md.refrescar_detalle("acme", 1)
    assert vistos == [True] and not r["cortado"] and "diario" in llamadas
    assert md._PLAZO.get() is None


def test_carga_inicial_escalonada_y_con_prioridad_baja(monkeypatch):
    """PND-117: encolar_todos no tira todos los experimentos a la vez delante del resto."""
    import meta_detalle as md
    encoladas = []
    monkeypatch.setattr(md.cola, "encolar", lambda tipo, payload, **kw: encoladas.append(kw) or 1)

    class Con:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, _q):
            class R:
                def all(self_inner):
                    return [(1, "acme"), (2, "acme"), (3, "otro")]
            return R()

    monkeypatch.setattr(md.db, "conectar", lambda: Con())
    assert md.encolar_todos() == 3
    desdes = [kw["ejecutar_desde"] for kw in encoladas]
    assert desdes == sorted(desdes) and len(set(desdes)) == 3
    assert all(kw["prioridad"] < 5 and kw["max_intentos"] == 2 for kw in encoladas)
