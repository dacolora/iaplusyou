"""PND-336 (decisión 2026-10-15, lote 3): centavos de Claude que se perdían en tareas. «Reescribir idea» y «pedidos»
no anotaban si fallaba el guardado después de pagar; «Sugerir con IA» perdía los tokens si la respuesta no traía lo
pedido; clasificar y copycoders escribían antes de anotar. Ahora, en los cuatro, lo que cobró Claude se anota apenas
responde, ANTES de guardar: si guardar falla, el gasto ya está (y el worker devuelve el cobro de lo que no llegó)."""
import json
from types import SimpleNamespace

import pytest

from nicho.avatares import costo_real


def _gasto(referencia):
    import gastos
    return next((g for g in gastos.historial("acme", limite=50) if g["referencia"] == referencia), None)


def test_reescribir_idea_anota_aunque_falle_guardarla(base_temporal, monkeypatch):
    import tareas
    from sprints import analisis, datos
    from tests.test_sprints_ideas import ANGULO, _ctx
    tareas.cargar_todas()
    _sid, cid, _rid = _ctx(monkeypatch, datos)
    cp = datos.crear_idea("acme", cid, "video", "Vieja", "escena vieja", gancho=ANGULO["gancho"],
                          extra={"angulo": dict(ANGULO)})
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: (
        json.dumps({"titulo": "Nueva", "escena": "Otra escena", "sonido": "agua"}), 900, 300))
    monkeypatch.setattr(datos, "actualizar_idea", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disco lleno")))
    with pytest.raises(RuntimeError, match="disco lleno"):
        tareas.REGISTRO["sprint_reescribir_idea"]({"id": 7, "payload": {"cliente": "acme", "cp_id": cp}})
    g = _gasto(f"idea:reescribir:{cp}:t7")
    assert g is not None and g["usd"] == pytest.approx(round(costo_real(900, 300), 4))


def test_pedidos_anota_aunque_falle_guardarlos(base_temporal, monkeypatch):
    import tareas
    from doctrina import pedidos, producto as dp
    from tests.test_doctrina_pedidos import _producto_con_piezas
    tareas.cargar_todas()
    fila = _producto_con_piezas(monkeypatch)
    monkeypatch.setattr(pedidos, "_llamar", lambda mensaje, system: (
        json.dumps({"pedidos": [{"texto": "Pega un comentario", "para_que": "prueba"}]}), 700, 900))
    monkeypatch.setattr(dp, "reemplazar_abiertos", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disco lleno")))
    with pytest.raises(RuntimeError, match="disco lleno"):
        tareas.REGISTRO["producto_pedidos"]({"id": 5, "payload": {"cliente": "acme", "producto_id": fila}})
    g = _gasto(f"producto:pedidos:{fila}:t5")
    assert g is not None and g["usd"] == pytest.approx(round(costo_real(700, 900), 4))


class _Uso:
    input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens = 500, 60, 0, 0


def _claude_que_responde(texto):
    class _Cliente:
        def __init__(self, **kw):
            self.messages = self

        def create(self, **kw):
            return SimpleNamespace(usage=_Uso(), stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text=texto)])
    return _Cliente


@pytest.mark.parametrize("respuesta", ['{"elegidos": {"referente_id": 5}}', '{"elegidos": "5"}',
                                       '{"elegidos": [5, "x"]}', '{"elegidos": 7}'])
def test_sugerir_con_ia_no_pierde_los_tokens_si_la_respuesta_no_trae_objetos(monkeypatch, respuesta):
    from referentes import sugerir
    monkeypatch.setattr(sugerir.anthropic, "Anthropic", _claude_que_responde(respuesta))
    monkeypatch.setattr(sugerir, "_api_key", lambda: "k")
    candidatos = [{"id": 5, "familia": "ugc", "dolor": "d", "firma": "f", "dias": 3, "variantes": 2}]
    try:
        elegidos, ent, sal = sugerir.sugerir_ia(candidatos, "p", "pr", "t", 2)
    except sugerir.SugerenciaInvalida as e:
        assert (e.tokens_entrada, e.tokens_salida) == (500, 60)          # el llamador anota lo pagado
    else:
        assert elegidos == [] and (ent, sal) == (500, 60)


def _referente(datos, cliente, bid, anuncio="9"):
    rid, _ = datos.guardar_referente({"anuncio_id": anuncio, "fuente": "atria", "imagen_origen": "https://x/9.jpg",
                                      "marca": "M", "titular": "T", "cuerpo": "", "idioma": "en"},
                                     cliente=cliente, barrido_id=bid)
    datos.marcar_imagen(rid, "ok", "https://r2/9.jpg")
    return rid


@pytest.mark.parametrize("valida", [True, False])
def test_clasificar_anota_antes_de_escribir_el_referente(base_temporal, monkeypatch, valida):
    from referentes import clasificar, datos
    from tareas import referentes as tareas_ref
    bid = datos.crear_barrido("acme", "atria", {}, 5)
    rid = _referente(datos, "acme", bid)
    if valida:
        monkeypatch.setattr(clasificar, "clasificar", lambda referente, vocabulario: (
            {"etapa": "TOF", "consciencia": "unaware", "familia": None, "familia_nueva": {"nombre": "X", "descripcion": "d"},
             "dolor": "d", "firma": "f"}, 900, 60))
    else:
        def _invalida(referente, vocabulario):
            e = clasificar.ClasificacionInvalida("Claude no devolvió JSON.")
            e.tokens_entrada, e.tokens_salida = 900, 60
            raise e
        monkeypatch.setattr(clasificar, "clasificar", _invalida)
    monkeypatch.setattr(datos, "actualizar_referente", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disco lleno")))
    monkeypatch.setattr(tareas_ref.cola, "reportar", lambda *a, **k: None)
    tarea = {"id": 3, "payload": {"cliente": "acme", "barrido_id": bid, "fase": "clasificando",
                                  "consulta": {"fuente": "atria"}, "tope": 5}}
    with pytest.raises(RuntimeError, match="disco lleno"):
        tareas_ref.ejecutar_barrer(tarea)
    g = _gasto(f"referentes:clasificar:{rid}:t3")
    assert g is not None and g["usd"] == pytest.approx(round(costo_real(900, 60), 4))


@pytest.mark.parametrize("paso", ["firmas", "familias"])
def test_copycoders_anota_antes_de_escribir(base_temporal, monkeypatch, paso):
    import gastos
    from referentes import copycoders, datos
    from tareas import referentes as tr
    from tests.test_tareas_referentes import _sembrar_sin_traducir
    bid = datos.crear_barrido(None, "copycoders", {"url": copycoders.URL_SWIPE}, 0)
    monkeypatch.setattr(tr.cola, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(tr.cola, "encolar", lambda *a, **k: 1)
    monkeypatch.setattr(copycoders, "traducir_firmas", lambda pares: ({rid: f"ES {f}" for rid, f in pares}, 100, 40))
    monkeypatch.setattr(copycoders, "describir_familias", lambda fams: ({n: f"Desc {n}" for n, _ in fams}, 30, 10))
    if paso == "firmas":
        _sembrar_sin_traducir(datos, bid, 2)
        monkeypatch.setattr(datos, "marcar_traducidas", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disco lleno")))
    else:
        datos.familia_asegurar("Sin descripción", "")
        monkeypatch.setattr(datos, "familia_actualizar", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disco lleno")))
    with pytest.raises(RuntimeError, match="disco lleno"):
        tr.ejecutar_importar({"id": 4, "job_id": tr.JOB_IMPORTAR,
                              "payload": {"url": copycoders.URL_SWIPE, "barrido_id": bid, "fase": "traducir"}})
    filas = [g for g in gastos.historial(datos.CLIENTE_CREATV, limite=20) if "copycoders:traduccion" in g["referencia"]]
    assert filas and all(g["usd"] > 0 for g in filas)
