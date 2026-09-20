import json

import pytest


def _c(i, fuente="texto", puntuacion=None, fecha=None, texto=None, excluido=False):
    return {"id": i, "fuente": fuente, "puntuacion": puntuacion, "fecha": fecha, "excluido": excluido,
            "contexto": None, "texto": texto or f"Comentario {i} sobre la garrafa que pesa y gotea en el estante."}


def test_seleccionar_excluye_ordena_y_alterna_fuentes():
    from nicho import avatares
    lista = [_c(1, "texto", puntuacion=1), _c(2, "texto", puntuacion=9), _c(3, "reddit", puntuacion=5),
             _c(4, "reddit", puntuacion=5, fecha="2026-02-01"), _c(5, "youtube", excluido=True), _c(6, "youtube")]
    sel = avatares.seleccionar(lista)
    assert [c["id"] for c in sel] == [4, 2, 6, 3, 1]      # ronda reddit/texto/youtube; dentro: puntuación desc, fecha desc, id
    assert [c["id"] for c in avatares.seleccionar(lista, max_n=2)] == [4, 2]
    corto = avatares.seleccionar(lista, max_caracteres=len(lista[0]["texto"]) * 2 + 1)
    assert len(corto) == 2
    assert avatares.seleccionar([]) == []


def test_estimar_costo_y_costo_real(monkeypatch):
    from nicho import avatares
    lista = [_c(i, texto="x" * 350) for i in range(1, 21)]           # 20 comentarios × 350 caracteres = 7 000 chars
    e = avatares.estimar_costo(lista, modelo="claude-sonnet-5")
    tokens_texto = int(7000 * avatares.TOKENS_POR_CARACTER)
    assert e["comentarios"] == 20 and e["suficientes"] is True and e["referencia"] is False and e["modelo"] == "claude-sonnet-5"
    assert e["tokens_entrada"] == tokens_texto * 2 + avatares.TOKENS_PROMPT * (1 + avatares.MAX_NUCLEOS)
    assert e["tokens_salida"] == avatares.TOKENS_SALIDA_ESTIMADO_NUCLEOS + avatares.TOKENS_SALIDA_ESTIMADO_SUBS * avatares.MAX_NUCLEOS
    esperado = (e["tokens_entrada"] * 2.0 + e["tokens_salida"] * 10.0) / 1e6
    assert e["usd"] >= esperado and e["usd"] - esperado < 0.01           # redondeado hacia arriba al centavo
    assert avatares.estimar_costo(lista[:5], modelo="claude-sonnet-5")["suficientes"] is False
    raro = avatares.estimar_costo(lista, modelo="claude-desconocido-9")
    assert raro["referencia"] is True and raro["usd"] >= e["usd"]         # precio de referencia = el más caro
    assert avatares.costo_real(1_000_000, 100_000, modelo="claude-sonnet-5") == pytest.approx(3.0)
    monkeypatch.setattr(avatares, "modelo_actual", lambda: "claude-haiku-4-5")
    assert avatares.costo_real(1_000_000, 0) == pytest.approx(1.0) and avatares.estimar_costo(lista)["modelo"] == "claude-haiku-4-5"


NUCLEOS_JSON = {"nucleos": [
    {"nombre": "Lavar sin cargar peso", "deseo": "Quiero que lavar sea fácil y que limpie bien", "resumen": "Gente cansada de garrafas", "comentarios": [1, 2, 2, 99, "3"]},
    {"nombre": "Repetido", "deseo": "Quiero lo mismo", "resumen": "", "comentarios": [1]},
    {"nombre": "", "deseo": "sin nombre", "comentarios": [4]},
    {"nombre": "Sin comentarios válidos", "deseo": "Quiero", "comentarios": [77]},
]}
SUB_JSON = {"sub_avatares": [
    {"base": "experiencia_producto", "nombre": "Ana / La que carga la garrafa", "deseo": "Quiero lavar sin cargar",
     "demografia": "", "edad_rango": "", "emocion": "Frustración cada semana",
     "identidad": {"quiere_que_vean": "organizada", "cree_de_si": "práctica", "quiere_lograr": "una casa que funcione"},
     "soluciones_previas": [{"que": "Detergente líquido de marca", "por_que_fallo": ["Pesado de cargar", "Gotea en el estante"]}],
     "situaciones": ["Cargando garrafas de 2 litros desde el súper"], "comportamiento": "Sigue comprando líquido porque es lo probado",
     "conciencia": {"nivel": "consciente_del_problema", "detalle": "Sabe que pesa, no sabe que hay otra cosa"},
     "encaje_producto": "Cápsulas: nada que cargar", "tono": "Directo, con humor cansado", "palabras_clave": ["garrafa", "peso"],
     "evidencia": [{"comentario_id": 1, "cita": "la garrafa PESA demasiado"}, {"comentario_id": 2, "cita": "esto no lo dijo nadie"},
                   {"comentario_id": 1, "cita": "corta"}, {"comentario_id": 5, "cita": "la garrafa pesa demasiado"}]},
    {"base": "otra", "nombre": "Sin deseo", "deseo": ""},
    {"base": "emocion", "nombre": "Sin evidencia", "deseo": "Quiero algo", "conciencia": {"nivel": "inventado"}, "evidencia": []},
]}


def test_parsear_nucleos():
    from nicho import avatares
    n = avatares.parsear_nucleos("```json\n" + json.dumps(NUCLEOS_JSON) + "\n```", ids_validos={1, 2, 3, 4})
    assert [x["nombre"] for x in n] == ["Lavar sin cargar peso"]
    assert n[0]["comentarios"] == [1, 2, 3] and n[0]["resumen"] == "Gente cansada de garrafas"
    with pytest.raises(avatares.AnalisisInvalido):
        avatares.parsear_nucleos("no es json", {1})
    with pytest.raises(avatares.AnalisisInvalido):
        avatares.parsear_nucleos(json.dumps({"nucleos": []}), {1})
    with pytest.raises(avatares.AnalisisInvalido):
        avatares.parsear_nucleos(json.dumps({"otra": 1}), {1})
    assert len(avatares.parsear_nucleos(json.dumps({"nucleos": [{"nombre": f"N{i}", "deseo": "Q", "comentarios": [i]} for i in range(9)]}), set(range(9)))) == avatares.MAX_NUCLEOS


def test_parsear_subs_y_verificar_evidencia():
    from nicho import avatares
    subs = avatares.parsear_subs(json.dumps(SUB_JSON))
    assert [s["nombre"] for s in subs] == ["Ana / La que carga la garrafa", "Sin evidencia"]
    s = subs[0]
    assert s["base"] == "experiencia_producto" and s["conciencia"]["nivel"] == "consciente_del_problema"
    assert s["soluciones_previas"][0]["por_que_fallo"] == ["Pesado de cargar", "Gotea en el estante"] and s["palabras_clave"] == ["garrafa", "peso"]
    assert len(s["evidencia"]) == 4
    assert subs[1]["base"] == "emocion" and subs[1]["conciencia"] == {"nivel": "", "detalle": ""} and subs[1]["identidad"] == {"quiere_que_vean": "", "cree_de_si": "", "quiere_lograr": ""}
    por_id = {1: _c(1, texto="Sí, la garrafa   pesa demasiado, gotea y la tapa se pega."), 2: _c(2, texto="Otro comentario cualquiera.")}
    v = avatares.verificar_evidencia(s, por_id)
    assert v["evidencia"] == [{"comentario_id": 1, "cita": "la garrafa PESA demasiado"}] and v["sin_evidencia"] is False
    v2 = avatares.verificar_evidencia(subs[1], por_id)
    assert v2["evidencia"] == [] and v2["sin_evidencia"] is True
    with pytest.raises(avatares.AnalisisInvalido):
        avatares.parsear_subs(json.dumps({"sub_avatares": [{"nombre": "", "deseo": ""}]}))


def test_prompts_incluyen_contexto():
    from nicho import avatares
    estudio = {"nombre": "Detergente", "producto": "Cápsulas sin plástico", "tema": "lavar en casa, Suecia", "idioma": "sv"}
    comentarios = [_c(1, "reddit", puntuacion=34, texto="La garrafa pesa demasiado"), _c(2, texto="Gotea")]
    comentarios[0]["contexto"] = "Foot pains thread"
    p1 = avatares.armar_prompt_nucleos(estudio, comentarios, marca_nombre="Happy Wash")
    for frag in ("Happy Wash", "Cápsulas sin plástico", "lavar en casa, Suecia", "[1] (reddit · 34 · Foot pains thread) La garrafa pesa demasiado",
                 "[2] (texto) Gotea", "sueco", str(avatares.MAX_NUCLEOS), '"nucleos"'):
        assert frag in p1, frag
    nucleo = {"nombre": "Lavar sin cargar", "deseo": "Quiero lavar sin cargar", "resumen": "Gente cansada"}
    p2 = avatares.armar_prompt_subs(estudio, nucleo, comentarios[:1], guia="Luz natural, tono cercano", marca_nombre="Happy Wash")
    for frag in ("Lavar sin cargar", "Quiero lavar sin cargar", "Gente cansada", "Luz natural, tono cercano", "Beliefs about self",
                 "consciente_del_problema", '"sub_avatares"', "[1] (reddit · 34 · Foot pains thread) La garrafa pesa demasiado", "sueco"):
        assert frag in p2, frag
    assert "[2]" not in p2
    assert avatares.nombre_idioma("xx") == "xx" and avatares.nombre_idioma("es") == "español"
