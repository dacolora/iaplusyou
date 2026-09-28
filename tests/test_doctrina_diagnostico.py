"""Doctrina, bloque 4: el diagnóstico de una pieza perdedora."""
import json

import pytest

REGLAS = {"thruplay_min": 0.25, "ctr_min": 1.0, "cpc_max": 0.5}
ANGULO = {"audiencia": "quien trabaja en casa con frío", "consciencia": "consciente_del_problema", "sofisticacion": 2,
          "deseo": "pies calientes", "promesa": "pies calientes toda la mañana", "mecanismo": None, "pruebas": [],
          "lead": "problema_solucion", "gancho": "¿Pies fríos en casa?", "faltantes": []}
PZ = {"id": 7, "nombre": "Pantuflas en la oficina", "pais": "CO", "es_imagen": False, "angulo": ANGULO}
VEREDICTO = {"veredicto": "perdedor", "motivo": "No pasó la puerta de tráfico: ThruPlay 8% < 25%.", "accion": "rescatar",
             "puerta": 1, "numeros": {"impresiones": 1200, "ctr": 0.4, "thruplay_rate": 0.08}}


def _snap(**k):
    base = {"impresiones": 1200, "ctr": 1.5, "cpc": 0.3, "thruplay_rate": 0.4, "frecuencia": 1.2, "compras": 0}
    base.update(k)
    return [base]


def _codigos(lista):
    return [p["codigo"] for p in lista]


def test_pistas_por_metricas():
    from doctrina import diagnostico as dg
    assert dg.pistas([], REGLAS, {}) == []
    assert dg.pistas(_snap(), REGLAS, {}) == []                                       # todo dentro de umbral
    assert _codigos(dg.pistas(_snap(thruplay_rate=0.08), REGLAS, {})) == ["gancho"]
    assert _codigos(dg.pistas(_snap(ctr=0.4), REGLAS, {})) == ["sin_urgencia"]        # retiene pero no clican
    assert _codigos(dg.pistas(_snap(ctr=0.4, thruplay_rate=0.08), REGLAS, {})) == ["gancho"]   # el gancho manda
    assert _codigos(dg.pistas(_snap(ctr=0.4, thruplay_rate=0.08), REGLAS, {"es_imagen": True})) == ["sin_urgencia"]
    assert _codigos(dg.pistas(_snap(), REGLAS, {"puerta": 2})) == ["landing"]
    assert _codigos(dg.pistas(_snap(frecuencia=3.4), REGLAS, {})) == ["repeticion"]
    assert _codigos(dg.pistas(_snap(cpc=0.9), REGLAS, {})) == ["subasta_cara"]
    assert _codigos(dg.pistas(_snap(cpc=0.9, ctr=0.4), REGLAS, {})) == ["sin_urgencia"]        # CPC alto con CTR bajo no es la subasta
    p = dg.pistas(_snap(thruplay_rate=0.08, frecuencia=4), REGLAS, {})
    assert _codigos(p) == ["gancho", "repeticion"] and "ThruPlay 8 %" in p[0]["texto"] and "4.0 veces" in p[1]["texto"]
    assert dg.pistas(_snap(thruplay_rate=0.08), {"thruplay_min": None, "ctr_min": None, "cpc_max": None}, {}) == []


def _respuesta(**cambios):
    data = {"causas": [{"codigo": "gancho", "detalle": "Nadie pasa del segundo 3.", "evidencia": "ThruPlay 8 %"},
                       {"codigo": "sin_urgencia", "detalle": "El deseo no aprieta.", "evidencia": "CTR 0,4 %"}],
            "siguiente": {"que": "gancho", "porque": "el mensaje no se alcanzó a ver", "hipotesis": "otro arranque retiene"},
            "aprendizaje": "En CO el arranque problema-solución con «¿Pies fríos?» no retuvo."}
    data.update(cambios)
    return "Va: " + json.dumps(data, ensure_ascii=False)


def test_parsear_limpia_y_exige_causa_y_siguiente():
    from doctrina import diagnostico as dg
    d = dg.parsear(_respuesta(causas=[{"codigo": "gancho", "detalle": "x", "evidencia": "y"},
                                      {"codigo": "inventada", "detalle": "z"},
                                      {"codigo": "gancho", "detalle": "repetida"}]))
    assert [c["codigo"] for c in d["causas"]] == ["gancho"] and d["siguiente"]["que"] == "gancho"
    assert d["aprendizaje"].startswith("En CO")
    for texto, parte in (("nada", "JSON"), ('{"a": }', "inválido"), (_respuesta(causas=[]), "ninguna causa"),
                         (_respuesta(siguiente={"que": "rezar"}), "no existe")):
        with pytest.raises(dg.ErrorDiagnostico) as e:
            dg.parsear(texto)
        assert parte in str(e.value)


def _preparar(monkeypatch, respuestas):
    from sprints import analisis
    llamadas = []

    def falso(content, max_tokens=700, system=None):
        llamadas.append({"content": content, "max_tokens": max_tokens, "system": system})
        r = respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r, 900, 350
    monkeypatch.setattr(analisis, "_llamar_contando", falso)
    return llamadas


def test_diagnosticar_arma_los_datos_y_devuelve_tokens(monkeypatch):
    import doctrina
    from doctrina import diagnostico as dg
    llamadas = _preparar(monkeypatch, [_respuesta()])
    extras = {"guion": {"bloques": [{"rol": "hook", "texto_voz": "¿Frío otra vez?"}]},
              "producto": {"nombre": "Hcozy", "sofisticacion": 2},
              "revision": {"puntos": [{"n": 6, "estado": "mejorar", "detalle": "El producto no se ve."}]},
              "dias_transcurridos": 3}
    d, ent, sal = dg.diagnosticar(PZ, VEREDICTO, _snap(thruplay_rate=0.08, ctr=0.4), REGLAS, extras)
    assert (ent, sal) == (900, 350) and len(llamadas) == 1
    assert d["siguiente"]["que"] == "gancho" and [c["codigo"] for c in d["causas"]] == ["gancho", "sin_urgencia"]
    assert _codigos(d["pistas"]) == ["gancho"]
    l = llamadas[0]
    assert l["max_tokens"] == dg.MAX_TOKENS and doctrina.texto("diagnosticar")[:40] in l["system"][0]["text"]
    assert "sin_urgencia" in l["system"][1]["text"] and "pausar" in l["system"][1]["text"]
    texto = l["content"][0]["text"]
    for frag in ("<datos>", "VEREDICTO DEL MOTOR: No pasó", "ThruPlay 8 %", "¿Pies fríos en casa?", "punto 6",
                 "hook: ¿Frío otra vez?", "Hcozy", "DÍAS CORRIDOS: 3", "</datos>"):
        assert frag in texto, frag


def test_diagnosticar_corrige_una_vez_y_no_pierde_lo_pagado(monkeypatch):
    from doctrina import diagnostico as dg
    llamadas = _preparar(monkeypatch, ["nada", _respuesta()])
    d, ent, sal = dg.diagnosticar(PZ, VEREDICTO, _snap(), REGLAS)
    assert (ent, sal) == (1800, 700) and "no sirvió" in llamadas[1]["content"][-1]["text"]
    _preparar(monkeypatch, ["nada", "tampoco"])
    with pytest.raises(dg.ErrorDiagnostico) as e:
        dg.diagnosticar(PZ, VEREDICTO, _snap(), REGLAS)
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (1800, 700)
    _preparar(monkeypatch, ["nada", RuntimeError("red caída")])
    with pytest.raises(dg.ErrorDiagnostico) as e:
        dg.diagnosticar(PZ, VEREDICTO, _snap(), REGLAS)
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (900, 350)


def test_decision_de_rescate_segun_el_diagnostico():
    from doctrina import diagnostico as dg
    base = dg.parsear(_respuesta())
    assert dg.decision_rescate(base) == {"salto": None, "solo_proponer": False,
                                         "motivo": "Diagnóstico: el gancho no retiene, sin urgencia en el deseo — "
                                                   "siguiente: gancho (el mensaje no se alcanzó a ver)"}
    assert dg.decision_rescate(dg.parsear(_respuesta(siguiente={"que": "estructura", "porque": "p"})))["salto"] == 2
    assert dg.decision_rescate(dg.parsear(_respuesta(siguiente={"que": "regenerar"})))["salto"] == 3
    d = dg.decision_rescate(dg.parsear(_respuesta(siguiente={"que": "landing", "porque": "clican y no compran"})))
    assert d["solo_proponer"] is True and d["salto"] is None and "decide tú" in d["motivo"]
    d = dg.decision_rescate(dg.parsear(_respuesta(causas=[{"codigo": "estacionalidad", "detalle": "x"}],
                                                  siguiente={"que": "gancho"})))
    assert d["solo_proponer"] is True                         # la causa principal no es del creativo
    assert dg.decision_rescate(None) == {"salto": None, "solo_proponer": False, "motivo": ""}
    assert dg.decision_rescate({"error": "x"})["solo_proponer"] is False
