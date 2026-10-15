"""PND-315 (decisión 2026-10-13, lote 1): cada llamada anota lo que de verdad cobró el proveedor: la revisión de
marca de cada swap (no anotaba nada; «Analizar marca» la pasa a cobrarse la rama l1-cobros, PND-299), la regla de fidelidad que vuelve vacía y la palabra
que no se pudo traducir (tampoco), Gemini con sus reintentos (anotaba uno), `caption_organico` (0,01 fijo) y
Nicho con Apify (un estimado sin conciliar con `usageTotalUsd`). El upscaler está en test_tareas_swap."""
import json
import types

import pytest
import sqlalchemy as sa

import db
import generador_prompts as gp
from nicho.avatares import costo_real

pytestmark = pytest.mark.usefixtures("margen_1_5")


class _Uso:
    def __init__(self, entrada=2000, salida=500):
        self.input_tokens, self.output_tokens = entrada, salida
        self.cache_creation_input_tokens = self.cache_read_input_tokens = 0


def _claude(monkeypatch, texto, uso=None, stop="end_turn"):
    """Anthropic falso para generador_prompts: responde `texto` con `uso`."""
    class _Cliente:
        def __init__(self, api_key=None, **kw):
            self.messages = self

        def create(self, **kw):
            return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=texto)],
                                         usage=uso or _Uso(), stop_reason=stop)
    monkeypatch.setattr(gp.anthropic, "Anthropic", _Cliente)
    monkeypatch.setattr(gp, "_api_key", lambda: "sk-test")


def _gastos(cliente="acme"):
    with db.conectar() as con:
        return {f.referencia: dict(f._mapping) for f in con.execute(sa.select(db.gasto)
                                                                    .where(db.gasto.c.cliente == cliente))}


def _movs(gasto_id):
    m = db.movimiento_saldo
    with db.conectar() as con:
        return [r.tipo for r in con.execute(sa.select(m.c.tipo).where(m.c.gasto_id == gasto_id))]


def test_contar_uso_junta_lo_de_cada_llamada(monkeypatch):
    _claude(monkeypatch, "Mismo azul.", _Uso(3000, 400))
    with gp.contar_uso() as usos:
        gp.regla_fidelidad("Cojín", "lino", "Hogar")
    assert gp.usd_de(usos) == costo_real(3000, 400) > 0
    gp.regla_fidelidad("Cojín", "lino", "Hogar")       # fuera del bloque no junta nada (ni falla)


# ------------------------------------------------- revisión de marca del swap ---

def test_la_revision_de_marca_del_swap_anota_lo_que_cobro_claude(base_temporal, monkeypatch):
    import tareas.swap as sw
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    _claude(monkeypatch, json.dumps([{"puntaje": 90, "motivo": "bien"}]), _Uso(2500, 300))
    monkeypatch.setattr(sw.marca_mod, "cargar_root", lambda c: {"invariants": [{"id": 1, "name": "logo", "rule": "x"}]})
    monkeypatch.setattr(sw.swaps_mod, "actualizar", lambda *a, **k: True)
    monkeypatch.setattr(sw.bitacora, "registrar", lambda *a, **k: None)
    sw._evaluar_swap_contra_matriz("acme", "swap_1", "https://r2/x.png", ref_sufijo=":t4")
    g = _gastos()["revision_marca:swap_1:t4"]
    assert g["tipo"] == "revision" and g["usd"] == costo_real(2500, 300) and _movs(g["id"]) == ["cobro"]


def test_la_revision_de_marca_que_no_se_pudo_leer_se_anota_sin_cobrarla(base_temporal, monkeypatch):
    import tareas.swap as sw
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    _claude(monkeypatch, "no es json", _Uso(2500, 300))
    monkeypatch.setattr(sw.marca_mod, "cargar_root", lambda c: {"invariants": [{"id": 1, "name": "logo", "rule": "x"}]})
    monkeypatch.setattr(sw.swaps_mod, "actualizar", lambda *a, **k: True)
    monkeypatch.setattr(sw.bitacora, "registrar", lambda *a, **k: None)
    sw._evaluar_swap_contra_matriz("acme", "swap_1", "https://r2/x.png", ref_sufijo=":t4")
    g = _gastos()["revision_marca:swap_1:t4"]
    assert g["usd"] == costo_real(2500, 300) and _movs(g["id"]) == ["no_cobrado"]


# --------------------------------------------------- regla de fidelidad vacía ---

def test_la_regla_de_fidelidad_anota_lo_real_y_la_vacia_tambien(base_temporal, monkeypatch):
    import importador
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True, pospago=True)   # pospago: el freno no corta
    _claude(monkeypatch, "Mismo azul y el logo bordado.", _Uso(600, 120))
    assert importador._regla_y_gasto("acme", "p1", "Cojín", "lino", "Hogar") == "Mismo azul y el logo bordado."
    g = _gastos()["regla_producto:p1"]
    assert g["usd"] == costo_real(600, 120) and _movs(g["id"]) == ["cobro"]
    _claude(monkeypatch, "", _Uso(600, 200), stop="max_tokens")
    assert importador._regla_y_gasto("acme", "p2", "Manta", "lana", "Hogar") == ""
    g = _gastos()["regla_producto:p2"]
    assert g["usd"] == costo_real(600, 200) and _movs(g["id"]) == ["no_cobrado"]


# ------------------------------------------------------------ caption orgánico ---

def test_caption_organico_anota_lo_real(base_temporal, monkeypatch):
    """Lo real, no 0,01 fijo. Como toda ruta sincrónica a Claude (cobros §3.5), un texto que no sirvió igual se
    cobra: Claude respondió."""
    import organico
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True, pospago=True)   # pospago: el freno no corta
    monkeypatch.setattr(organico, "contexto_pieza", lambda c, pid: {"nombre_producto": "Chancla", "idioma": "es"})
    _claude(monkeypatch, json.dumps({"instagram": {"titulo": "T", "caption": "Hola"}}), _Uso(5000, 1500))
    organico.redactar("acme", "pz1", ["instagram"])
    (g,) = _gastos().values()
    assert g["usd"] == costo_real(5000, 1500) and _movs(g["id"]) == ["cobro"]
    _claude(monkeypatch, "sin json", _Uso(5000, 1500))
    organico.redactar("acme", "pz2", ["instagram"])
    (g2,) = [g for r, g in _gastos().items() if ":pz2:" in r]
    assert g2["usd"] == costo_real(5000, 1500) and _movs(g2["id"]) == ["cobro"]


# ------------------------------------------------------- la palabra sin traducir ---

def test_la_palabra_que_no_se_pudo_traducir_igual_anota_lo_cobrado(base_temporal, monkeypatch):
    from referentes import traducir
    _claude(monkeypatch, "", _Uso(120, 60), stop="max_tokens")
    with pytest.raises(traducir.TraduccionInvalida):
        traducir.preparar_consulta({"modo": "palabra", "palabra": "dolor de pies"}, "acme")
    (g,) = _gastos().values()
    assert g["usd"] == costo_real(120, 60) and g["referencia"].startswith("referentes:traducir:")


# ----------------------------------------------------------- Gemini y sus reintentos ---

class _RespGemini:
    def __init__(self, status=200, datos=None):
        self.status_code, self._datos = status, datos or {}
        self.text = json.dumps(self._datos)

    def raise_for_status(self):
        import requests
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(str(self.status_code))

    def json(self):
        return self._datos


def test_gemini_anota_cada_intento_que_pudo_cobrar(monkeypatch):
    import base64

    import requests
    from providers import nano_banana_client as nb
    monkeypatch.setattr(nb, "_api_key", lambda: "k")
    imagen = {"candidates": [{"content": {"parts": [{"inlineData": {"data": base64.b64encode(b"png").decode()}}]}}]}
    respuestas = [requests.exceptions.ReadTimeout("lento"),          # pudo generarse y cobrarse
                  requests.exceptions.ConnectionError("sin red"),    # no llegó: no cobra
                  _RespGemini(200, imagen)]

    def post(*a, **k):
        r = respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    monkeypatch.setattr(nb.requests, "post", post)
    cobrado = []
    assert nb._llamar([{"text": "x"}], on_cobro=lambda usd, entregado: cobrado.append((usd, entregado))) == b"png"
    assert cobrado == [(nb.COSTO_USD_POR_IMAGEN, False), (nb.COSTO_USD_POR_IMAGEN, True)]


def test_gemini_sin_imagen_cobra_lo_que_leyo(monkeypatch):
    from providers import nano_banana_client as nb
    monkeypatch.setattr(nb, "_api_key", lambda: "k")
    monkeypatch.setattr(nb.requests, "post", lambda *a, **k: _RespGemini(200, {
        "candidates": [{"content": {"parts": [{"text": "no puedo"}]}}],
        "usageMetadata": {"promptTokenCount": 3000, "candidatesTokenCount": 10}}))
    cobrado = []
    with pytest.raises(RuntimeError):
        nb._llamar([{"text": "x"}], on_cobro=lambda usd, entregado: cobrado.append((usd, entregado)))
    assert cobrado == [(pytest.approx(nb.costo_tokens(3000, 10)), False)] and cobrado[0][0] > 0


def test_el_swap_de_gemini_cobra_solo_el_intento_que_entrego(base_temporal, monkeypatch, tmp_path):
    """Revisión de guardian-gasto: los intentos que pudieron cobrar sin entregar van en su propia fila, sin
    cobrarlos; al cliente solo se le cobra el que entregó la imagen."""
    from tests.test_tareas_swap import _swap_foto_listo
    import tareas.swap as sw
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    payload = _swap_foto_listo(sw, monkeypatch, tmp_path, swap_id="swap_g")

    def swap_producto(*a, on_cobro=None, **k):
        on_cobro(0.039, False)
        on_cobro(0.039, True)
        return b"png"
    monkeypatch.setattr(sw.nano_banana_client, "swap_producto", swap_producto)
    monkeypatch.setattr(sw.swaps_mod, "actualizar", lambda *a, **k: True)
    sw.ejecutar({"id": 2, "job_id": "acme__swap_g__swap", "payload": payload})
    g = _gastos()
    assert g["swap:swap_g:t2"]["usd"] == pytest.approx(0.039) and _movs(g["swap:swap_g:t2"]["id"]) == ["cobro"]
    assert g["swap:swap_g:t2:intentos"]["usd"] == pytest.approx(0.039)
    assert _movs(g["swap:swap_g:t2:intentos"]["id"]) == ["no_cobrado"]


def test_el_swap_de_gemini_que_falla_anota_los_intentos_sin_cobrarlos(base_temporal, monkeypatch, tmp_path):
    from tests.test_tareas_swap import _swap_foto_listo
    import tareas.swap as sw
    payload = _swap_foto_listo(sw, monkeypatch, tmp_path, swap_id="swap_h")

    def swap_producto(*a, on_cobro=None, **k):
        on_cobro(0.039, False)
        on_cobro(0.039, False)
        raise RuntimeError("Nano Banana no respondió después de 3 intentos")
    monkeypatch.setattr(sw.nano_banana_client, "swap_producto", swap_producto)
    monkeypatch.setattr(sw.swaps_mod, "actualizar", lambda *a, **k: True)
    with pytest.raises(RuntimeError):
        sw.ejecutar({"id": 2, "job_id": "acme__swap_h__swap", "payload": payload})
    g = _gastos()
    assert g["swap:swap_h:t2:intentos"]["usd"] == pytest.approx(0.078) and "swap:swap_h:t2" not in g


# ---------------------------------------------------------- Nicho con Apify ---

def test_nicho_concilia_con_lo_que_dice_apify(base_temporal):
    from nicho.fuentes import plataformas
    actor = {"actor": "a", "nombre": "x", "usd_por_resultado": 0.001, "usd_por_corrida": 0.0}
    sin_conciliar = [{"run_id": "r1"}, {"run_id": "r2", "usd_real": 0.5}]
    usd, extra = plataformas.costo_conciliado(10, sin_conciliar, actor)
    assert usd == plataformas.costo(10, 2, actor) and extra.get("conciliacion_pendiente")
    todas = [{"run_id": "r1", "usd_real": 0.30}, {"run_id": "r2", "usd_real": 0.25}]
    usd, extra = plataformas.costo_conciliado(10, todas, actor)
    assert usd == 0.55 and extra["usd_apify"] == 0.55 and not extra.get("conciliacion_pendiente")
    # Si Apify reporta menos que los resultados × precio, manda lo mayor (como el barrido de referentes).
    usd, _ = plataformas.costo_conciliado(1000, todas, actor)
    assert usd == plataformas.costo(1000, 2, actor)


def test_correr_lote_toma_lo_que_cobro_cada_corrida_del_ultimo_sondeo(monkeypatch):
    """`usageTotalUsd` viene en la misma respuesta del sondeo que dice que la corrida terminó: sin pedidos de más."""
    from nicho.fuentes import _http
    from providers import apify
    from tests.test_apify_lote import _Resp, _Sesion
    monkeypatch.setattr(_http, "dormir", lambda s: None)
    s = _Sesion({"/runs": _Resp(201, {"data": {"id": "r1", "defaultDatasetId": "d1", "status": "RUNNING"}}),
                 "/actor-runs/r1": _Resp(200, {"data": {"id": "r1", "status": "SUCCEEDED", "defaultDatasetId": "d1",
                                                        "usageTotalUsd": 0.12}}),
                 "/datasets/d1/items": _Resp(200, [{"x": 1}])})
    res = apify.correr_lote(s, "tok", "actor", [{"entrada": {}, "max_items": 5, "max_usd": 1, "etiqueta": "e"}], "etapa")
    assert res["corridas"][0]["usd_real"] == 0.12


# ----------------------------------------------- la caché de la doctrina también se cobra ---

@pytest.mark.parametrize("modulo", ["referentes.clasificar", "referentes.recrear", "nicho.avatares"])
def test_la_cache_de_la_doctrina_cuenta_en_los_tokens_de_entrada(monkeypatch, modulo):
    """Auditoría de PND-013: clasificar, recrear, sugerir y avatares mandan la doctrina con caché y solo contaban
    `input_tokens`: escribirla cuesta 1,25× y leerla 0,1× (como `guiones.claude`), y se anotaba de menos."""
    import importlib
    mod = importlib.import_module(modulo)
    uso = types.SimpleNamespace(input_tokens=1000, output_tokens=100, cache_creation_input_tokens=4000,
                                cache_read_input_tokens=10000)
    resp = types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text="{}")], usage=uso,
                                 stop_reason="end_turn")

    class _Cliente:
        def __init__(self, *a, **k):
            self.messages = self

        def create(self, **kw):
            return resp
    import anthropic
    monkeypatch.setattr(anthropic, "Anthropic", _Cliente)
    monkeypatch.setattr(gp, "_api_key", lambda: "sk-test")
    if hasattr(mod, "_api_key"):
        monkeypatch.setattr(mod, "_api_key", lambda: "sk-test")
    _, entrada, salida = mod._llamar("hola", 100) if modulo != "referentes.clasificar" else mod._llamar("hola")
    assert (entrada, salida) == (1000 + 5000 + 1000, 100)
