"""guiones.refinador: reglas de `validar` (puro), datos aislados por cliente,
el hilo con Claude (siempre con un `llamar` falso), versiones y aprobación."""
import json
import os
from datetime import datetime, timedelta

import pytest
import sqlalchemy as sa

DIALOGO = 'Ana says: "This mirror changed my mornings."'
CLIP = f"""CLIP 3 of 8 — 12 seconds
START STATE: Ana holds the round LED mirror in a bright bathroom.
TIMED SCRIPT:
0-4s: {DIALOGO}
4-12s: She turns the mirror light on and smiles.
END STATE: held frame on Ana smiling."""
CLIP_CAMBIADO = CLIP.replace("bright bathroom", "warm bedroom")


def _llamar_fijo(respuesta, ent=1200, sal=900, registro=None):
    def llamar(system, messages):
        if registro is not None:
            registro.append({"system": system, "messages": messages})
        return respuesta, ent, sal
    return llamar


def _json(respuesta, prompt):
    return json.dumps({"respuesta": respuesta, "prompt": prompt}, ensure_ascii=False)


def _crear(cliente="acme", **kw):
    from guiones import refinador
    datos = {"texto": CLIP, "titulo": "Clip 3", "tipo": "clip", "contexto": "Guion del espejo LED",
             "texto_fijo": [DIALOGO]}
    datos.update(kw)
    return refinador.crear(cliente, **datos)


def _envejecer(mensaje_id, minutos=5):
    import db
    viejo = (datetime.now() - timedelta(minutes=minutos)).isoformat(timespec="seconds")
    with db.conectar() as con:
        con.execute(sa.update(db.guion_mensaje).where(db.guion_mensaje.c.id == mensaje_id).values(creado_en=viejo))


def _gastos(cliente="acme"):
    import gastos
    return gastos.historial(cliente)


# ------------------------------------------------------------- validar ---

def test_validar_clip_correcto_no_tiene_problemas():
    from guiones.refinador import validar
    assert validar(CLIP, [DIALOGO], "clip") == []


def test_validar_texto_vacio():
    from guiones.refinador import validar
    assert len(validar("   ", [], "libre")) == 1
    assert len(validar("", [])) == 1


def test_validar_fragmento_fijo_faltante_se_nombra():
    from guiones.refinador import validar
    problemas = validar(CLIP.replace("changed my mornings", "changed my life"), [DIALOGO], "clip")
    assert len(problemas) == 1
    assert "Ana says" in problemas[0]


def test_validar_fragmento_largo_se_recorta_en_el_mensaje():
    from guiones.refinador import validar
    largo = "x" * 300
    problemas = validar(CLIP, [largo])
    assert len(problemas) == 1 and len(problemas[0]) < 200


def test_validar_normaliza_espacios_y_comillas_curvas():
    from guiones.refinador import validar
    texto = "CLIP 1 of 2 — 8 seconds\nAna   says:\n  “This mirror changed my mornings.”\n"
    assert validar(texto, [DIALOGO]) == []
    fijo_curvo = "Ana says: “It’s   bright.”"
    assert validar('Ana says: "It\'s bright." and leaves.', [fijo_curvo]) == []


def test_validar_fragmento_distingue_mayusculas():
    from guiones.refinador import validar
    assert validar(CLIP.replace("Ana says", "ana says"), [DIALOGO]) != []


@pytest.mark.parametrize("cabecera, ok", [
    ("CLIP 1 of 3 — 5 seconds", True),
    ("CLIP 1 of 3 - 15 seconds", True),
    ("CLIP 2 of 3 – 10 seconds", True),
    ("CLIP 1 of 3 — 20 seconds", False),
    ("CLIP 1 of 3 - 4 seconds", False),
    ("clip 3 of 3 – 16 seconds", False),
])
def test_validar_duracion_de_la_cabecera(cabecera, ok):
    from guiones.refinador import validar
    problemas = validar(f"{cabecera}\nShe smiles. HARD CUT on a held frame.")
    assert (problemas == []) is ok


def test_validar_clip_final_exige_hard_cut():
    from guiones.refinador import validar
    assert len(validar("FINAL CLIP — 8 seconds\nShe waves. Held frame.")) == 1
    assert validar("FINAL CLIP — 8 seconds\nShe waves. hard cut on a held frame.") == []


@pytest.mark.parametrize("texto, ok", [
    ("She walks away. Fade to black.", False),
    ("She walks away, fade-to-black ending.", False),
    ("Slow dissolve to black.", False),
    ("She walks away. No fade to black.", True),
    ("Never dissolve to black here.", True),
    ("Do not fade to black; hold the frame.", True),
])
def test_validar_fundido_a_negro(texto, ok):
    from guiones.refinador import validar
    assert (validar(texto) == []) is ok


def test_validar_imagen_no_aplica_reglas_de_clip():
    from guiones.refinador import validar
    assert validar("A mirror on a wall, fade to black vignette. FINAL CLIP poster.", tipo="imagen") == []


# ---------------------------------------------------- crear / listar ---

def test_crear_y_obtener(base_temporal):
    from guiones import refinador
    p = _crear()
    assert p["version_n"] == 1 and p["estado"] == "abierto" and p["origen"] == "manual"
    assert p["texto_original"] == p["texto_vigente"] == CLIP
    assert p["texto_fijo"] == [DIALOGO] and p["problemas"] == []
    d = refinador.obtener("acme", p["id"])
    assert d["mensajes"] == [] and d["pendiente"] is False and d["titulo"] == "Clip 3"


def test_crear_texto_fijo_como_texto_con_lineas(base_temporal):
    p = _crear(texto_fijo=f"{DIALOGO}\n\n   \nOtra línea\n")
    assert p["texto_fijo"] == [DIALOGO, "Otra línea"]


def test_crear_sin_titulo_usa_la_primera_linea(base_temporal):
    p = _crear(titulo="")
    assert p["titulo"].startswith("CLIP 3 of 8")


def test_crear_texto_vacio_falla(base_temporal):
    from guiones import refinador
    with pytest.raises(refinador.DatoInvalido):
        refinador.crear("acme", "   ")


def test_crear_tipo_desconocido_queda_libre(base_temporal):
    assert _crear(tipo="raro")["tipo"] == "libre"


def test_listar_mas_nuevo_primero_con_conteo_y_aislado(base_temporal):
    import db
    from guiones import refinador
    a = _crear(titulo="A")
    b = _crear(titulo="B")
    assert [p["id"] for p in refinador.listar("acme")] == [b["id"], a["id"]]
    refinador.pedir_cambio("acme", a["id"], "Cambia el baño por una habitación")
    with db.conectar() as con:
        con.execute(sa.update(db.guion_prompt).where(db.guion_prompt.c.id == b["id"])
                    .values(actualizado_en="2020-01-01T00:00:00"))
    lista = refinador.listar("acme")
    assert [p["id"] for p in lista] == [a["id"], b["id"]]
    assert lista[0]["n_mensajes"] == 2 and lista[1]["n_mensajes"] == 0
    assert set(lista[0]) >= {"id", "titulo", "tipo", "origen", "estado", "version_n", "actualizado_en", "n_mensajes"}
    assert refinador.listar("otro") == []
    assert refinador.obtener("otro", a["id"]) is None


# -------------------------------------------------------- pedir_cambio ---

def test_pedir_cambio_crea_persona_y_pendiente(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "  Cambia el baño  ", usuario="admin")
    d = refinador.obtener("acme", p["id"])
    assert d["pendiente"] is True
    persona, claude = d["mensajes"]
    assert persona["rol"] == "persona" and persona["contenido"] == "Cambia el baño" and persona["estado"] == "ok"
    assert claude["id"] == mid and claude["rol"] == "claude" and claude["estado"] == "pendiente"


def test_pedir_cambio_vacio(base_temporal):
    from guiones import refinador
    p = _crear()
    with pytest.raises(refinador.DatoInvalido):
        refinador.pedir_cambio("acme", p["id"], "   ")


def test_pedir_cambio_con_pendiente_vivo_se_rechaza(base_temporal):
    from guiones import refinador
    p = _crear()
    refinador.pedir_cambio("acme", p["id"], "uno")
    with pytest.raises(refinador.Conflicto):
        refinador.pedir_cambio("acme", p["id"], "dos")


def test_pendiente_viejo_se_marca_error_y_libera_el_hilo(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "uno")
    _envejecer(mid)
    d = refinador.obtener("acme", p["id"])
    assert d["pendiente"] is False
    claude = d["mensajes"][-1]
    assert claude["estado"] == "error" and "Se interrumpió la respuesta" in claude["contenido"]
    otro = refinador.pedir_cambio("acme", p["id"], "dos")
    assert otro != mid


def test_pendiente_viejo_se_libera_tambien_sin_obtener(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "uno")
    _envejecer(mid)
    refinador.pedir_cambio("acme", p["id"], "dos")


def test_pedir_cambio_en_aprobado_pide_reabrir(base_temporal):
    from guiones import refinador
    p = _crear()
    refinador.aprobar("acme", p["id"])
    with pytest.raises(refinador.Conflicto, match="Reábrelo"):
        refinador.pedir_cambio("acme", p["id"], "uno")


def test_pedir_cambio_de_otro_cliente(base_temporal):
    from guiones import refinador
    p = _crear()
    with pytest.raises(refinador.NoExiste):
        refinador.pedir_cambio("otro", p["id"], "uno")


# ----------------------------------------------------------- responder ---

def test_responder_con_cambio_guarda_propuesta_y_gasto(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia el baño por una habitación cálida")
    registro = []
    refinador.responder(mid, llamar=_llamar_fijo(_json("Cambié el lugar.", CLIP_CAMBIADO), registro=registro))
    d = refinador.obtener("acme", p["id"])
    claude = d["mensajes"][-1]
    assert claude["estado"] == "ok" and claude["contenido"] == "Cambié el lugar."
    assert claude["propuesta"] == CLIP_CAMBIADO and claude["problemas"] == [] and claude["aplicada"] is False
    assert d["pendiente"] is False and d["texto_vigente"] == CLIP
    g = _gastos()
    assert len(g) == 1 and g[0]["tipo"] == "refinar_prompt" and g[0]["referencia"] == f"guiones:refinar:{mid}"
    assert g[0]["usd"] > 0 and g[0]["proveedor"] == "anthropic"
    assert g[0]["extra"]["tokens_entrada"] == 1200 and g[0]["extra"]["tokens_salida"] == 900 and g[0]["extra"]["modelo"]
    ultimo = registro[0]["messages"][-1]
    assert ultimo["role"] == "user"
    assert CLIP in ultimo["content"] and "habitación cálida" in ultimo["content"] and DIALOGO in ultimo["content"]
    assert "Guion del espejo LED" in ultimo["content"]
    assert "JSON" in registro[0]["system"]


def test_responder_sin_cambio(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "¿Cuánto dura este clip?")
    refinador.responder(mid, llamar=_llamar_fijo(_json("Dura 12 segundos.", None)))
    claude = refinador.obtener("acme", p["id"])["mensajes"][-1]
    assert claude["estado"] == "ok" and claude["propuesta"] is None and claude["contenido"] == "Dura 12 segundos."


def test_responder_prompt_identico_no_es_propuesta(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Revisa")
    refinador.responder(mid, llamar=_llamar_fijo(_json("Está bien así.", CLIP + "\n")))
    assert refinador.obtener("acme", p["id"])["mensajes"][-1]["propuesta"] is None


def test_responder_json_en_bloque_de_codigo(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia")
    refinador.responder(mid, llamar=_llamar_fijo("```json\n" + _json("Listo.", CLIP_CAMBIADO) + "\n```"))
    assert refinador.obtener("acme", p["id"])["mensajes"][-1]["propuesta"] == CLIP_CAMBIADO


def test_responder_json_invalido_es_error_pero_cobra(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia")
    refinador.responder(mid, llamar=_llamar_fijo("Claro, aquí va el prompt: ..."))
    claude = refinador.obtener("acme", p["id"])["mensajes"][-1]
    assert claude["estado"] == "error" and claude["propuesta"] is None and claude["contenido"]
    g = _gastos()
    assert len(g) == 1 and g[0]["referencia"] == f"guiones:refinar:{mid}" and g[0]["usd"] > 0
    assert claude["usd"] == pytest.approx(g[0]["usd"])


def test_responder_propuesta_que_rompe_texto_fijo_guarda_problemas(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia el diálogo")
    roto = CLIP.replace("changed my mornings", "is great")
    refinador.responder(mid, llamar=_llamar_fijo(_json("Cambié el diálogo.", roto)))
    claude = refinador.obtener("acme", p["id"])["mensajes"][-1]
    assert claude["estado"] == "ok" and claude["propuesta"] == roto
    assert len(claude["problemas"]) == 1 and "Ana says" in claude["problemas"][0]


def test_responder_excepcion_no_filtra_el_texto_del_error(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia")

    def revienta(system, messages):
        raise RuntimeError("401 invalid x-api-key sk-ant-SECRETO")
    refinador.responder(mid, llamar=revienta)
    claude = refinador.obtener("acme", p["id"])["mensajes"][-1]
    assert claude["estado"] == "error" and "SECRETO" not in claude["contenido"] and "sk-ant" not in claude["contenido"]
    assert _gastos() == []


def test_responder_error_con_tokens_cobrados_registra_gasto(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia")

    def cortada(system, messages):
        e = refinador.RespuestaFallida("La respuesta de Claude salió incompleta.")
        e.tokens_entrada, e.tokens_salida = 3000, 6000
        raise e
    refinador.responder(mid, llamar=cortada)
    claude = refinador.obtener("acme", p["id"])["mensajes"][-1]
    assert claude["estado"] == "error" and "incompleta" in claude["contenido"]
    assert len(_gastos()) == 1


def test_responder_mensaje_que_ya_no_esta_pendiente_no_hace_nada(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia")
    refinador.responder(mid, llamar=_llamar_fijo(_json("Listo.", CLIP_CAMBIADO)))
    llamadas = []
    refinador.responder(mid, llamar=_llamar_fijo(_json("Otra.", None), registro=llamadas))
    assert llamadas == []
    assert refinador.obtener("acme", p["id"])["mensajes"][-1]["contenido"] == "Listo."


def test_respuesta_tardia_no_revive_un_pendiente_vencido(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia")

    def tarda(system, messages):
        _envejecer(mid)
        refinador.obtener("acme", p["id"])
        return _json("Listo.", CLIP_CAMBIADO), 100, 100
    refinador.responder(mid, llamar=tarda)
    claude = refinador.obtener("acme", p["id"])["mensajes"][-1]
    assert claude["estado"] == "error" and claude["propuesta"] is None
    assert len(_gastos()) == 1


def test_responder_segunda_vuelta_lleva_el_historial(base_temporal):
    from guiones import refinador
    p = _crear()
    m1 = refinador.pedir_cambio("acme", p["id"], "Cambia el baño")
    refinador.responder(m1, llamar=_llamar_fijo(_json("Cambié el lugar.", CLIP_CAMBIADO)))
    refinador.usar_version("acme", p["id"], m1, 1)
    m2 = refinador.pedir_cambio("acme", p["id"], "Ahora que sonría más")
    registro = []
    refinador.responder(m2, llamar=_llamar_fijo(_json("Sin cambios.", None), registro=registro))
    msgs = registro[0]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert "Cambia el baño" in msgs[0]["content"]
    assert json.loads(msgs[1]["content"])["respuesta"].startswith("Cambié el lugar.")
    assert CLIP_CAMBIADO in msgs[2]["content"] and "sonría más" in msgs[2]["content"]


def test_responder_omite_turnos_con_error(base_temporal):
    from guiones import refinador
    p = _crear()
    m1 = refinador.pedir_cambio("acme", p["id"], "Mensaje que falló")
    refinador.responder(m1, llamar=_llamar_fijo("no json"))
    m2 = refinador.pedir_cambio("acme", p["id"], "Mensaje nuevo")
    registro = []
    refinador.responder(m2, llamar=_llamar_fijo(_json("Ok.", None), registro=registro))
    msgs = registro[0]["messages"]
    assert len(msgs) == 1 and "Mensaje nuevo" in msgs[0]["content"] and "falló" not in msgs[0]["content"]


# --------------------------------------------------------- usar_version ---

def _con_propuesta(propuesta=CLIP_CAMBIADO):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia")
    refinador.responder(mid, llamar=_llamar_fijo(_json("Listo.", propuesta)))
    return p, mid


def test_usar_version_aplica_y_marca(base_temporal):
    from guiones import refinador
    p, mid = _con_propuesta()
    d = refinador.usar_version("acme", p["id"], mid, 1)
    assert d["texto_vigente"] == CLIP_CAMBIADO and d["version_n"] == 2
    msgs = refinador.obtener("acme", p["id"])["mensajes"]
    assert [m["aplicada"] for m in msgs] == [False, True]


def test_usar_version_cas(base_temporal):
    from guiones import refinador
    p, mid = _con_propuesta()
    refinador.usar_version("acme", p["id"], mid, 1)
    with pytest.raises(refinador.Conflicto, match="recarga"):
        refinador.usar_version("acme", p["id"], mid, 1)


def test_usar_version_rechaza_propuesta_con_problemas(base_temporal):
    from guiones import refinador
    p, mid = _con_propuesta(CLIP.replace("changed my mornings", "is great"))
    with pytest.raises(refinador.Conflicto) as e:
        refinador.usar_version("acme", p["id"], mid, 1)
    assert e.value.problemas
    assert refinador.obtener("acme", p["id"])["version_n"] == 1


def test_usar_version_rechaza_fila_sin_propuesta_o_en_error(base_temporal):
    from guiones import refinador
    p = _crear()
    mid = refinador.pedir_cambio("acme", p["id"], "Cambia")
    refinador.responder(mid, llamar=_llamar_fijo("no json"))
    with pytest.raises(refinador.Conflicto):
        refinador.usar_version("acme", p["id"], mid, 1)
    persona = refinador.obtener("acme", p["id"])["mensajes"][0]["id"]
    with pytest.raises(refinador.Conflicto):
        refinador.usar_version("acme", p["id"], persona, 1)


def test_usar_version_none_vuelve_al_original(base_temporal):
    from guiones import refinador
    p, mid = _con_propuesta()
    refinador.usar_version("acme", p["id"], mid, 1)
    d = refinador.usar_version("acme", p["id"], None, 2)
    assert d["texto_vigente"] == CLIP and d["version_n"] == 3
    assert not any(m["aplicada"] for m in refinador.obtener("acme", p["id"])["mensajes"])


def test_usar_version_en_aprobado(base_temporal):
    from guiones import refinador
    p, mid = _con_propuesta()
    refinador.aprobar("acme", p["id"])
    with pytest.raises(refinador.Conflicto):
        refinador.usar_version("acme", p["id"], mid, 1)


def test_usar_version_de_otro_prompt(base_temporal):
    from guiones import refinador
    p, mid = _con_propuesta()
    otro = _crear(titulo="otro")
    with pytest.raises(refinador.Conflicto):
        refinador.usar_version("acme", otro["id"], mid, 1)


# --------------------------------------------------------------- editar ---

def test_editar_sube_version(base_temporal):
    from guiones import refinador
    p, mid = _con_propuesta()
    refinador.usar_version("acme", p["id"], mid, 1)
    d = refinador.editar("acme", p["id"], CLIP.replace("smiles", "laughs"), 2)
    assert d["version_n"] == 3 and "laughs" in d["texto_vigente"]
    assert not any(m["aplicada"] for m in refinador.obtener("acme", p["id"])["mensajes"])


def test_editar_con_problemas(base_temporal):
    from guiones import refinador
    p = _crear()
    with pytest.raises(refinador.Incumple) as e:
        refinador.editar("acme", p["id"], CLIP.replace(DIALOGO, "She is silent."), 1)
    assert e.value.problemas
    assert refinador.obtener("acme", p["id"])["version_n"] == 1


def test_editar_cas(base_temporal):
    from guiones import refinador
    p = _crear()
    with pytest.raises(refinador.Conflicto):
        refinador.editar("acme", p["id"], CLIP_CAMBIADO, 7)


# ------------------------------------------------------ aprobar/reabrir ---

def test_aprobar_y_reabrir(base_temporal):
    from guiones import refinador
    p = _crear()
    assert refinador.aprobar("acme", p["id"])["estado"] == "aprobado"
    with pytest.raises(refinador.Conflicto):
        refinador.editar("acme", p["id"], CLIP_CAMBIADO, 1)
    assert refinador.reabrir("acme", p["id"])["estado"] == "abierto"
    assert refinador.editar("acme", p["id"], CLIP_CAMBIADO, 1)["version_n"] == 2


def test_aprobar_rechaza_vigente_con_problemas(base_temporal):
    from guiones import refinador
    p = _crear(texto=CLIP + "\nFade to black.")
    with pytest.raises(refinador.Incumple) as e:
        refinador.aprobar("acme", p["id"])
    assert e.value.problemas


def test_aprobar_rechaza_con_pendiente(base_temporal):
    from guiones import refinador
    p = _crear()
    refinador.pedir_cambio("acme", p["id"], "Cambia")
    with pytest.raises(refinador.Conflicto):
        refinador.aprobar("acme", p["id"])


def test_aprobar_con_version_distinta(base_temporal):
    from guiones import refinador
    p = _crear()
    with pytest.raises(refinador.Conflicto):
        refinador.aprobar("acme", p["id"], version_n=5)
    assert refinador.aprobar("acme", p["id"], version_n=1)["estado"] == "aprobado"


def test_aprobar_de_otro_cliente(base_temporal):
    from guiones import refinador
    p = _crear()
    with pytest.raises(refinador.NoExiste):
        refinador.aprobar("otro", p["id"])


# ------------------------------------------------------- gastos y tablas ---

def test_estimar_refinar_prompt():
    import gastos
    r = gastos.estimar("refinar_prompt")
    assert r["usd"] and r["usd"] >= 0.03 and "aprox." in r["texto"]
    assert "refinar_prompt" in gastos.TIPOS


def test_migracion_0018_crea_y_quita_las_tablas(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig18.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    command.upgrade(cfg, "head")
    insp = sa.inspect(db.engine())
    assert {"guion_prompt", "guion_mensaje"} <= set(insp.get_table_names())
    assert {c["name"] for c in insp.get_columns("guion_prompt")} == {c.name for c in db.guion_prompt.columns}
    assert {c["name"] for c in insp.get_columns("guion_mensaje")} == {c.name for c in db.guion_mensaje.columns}
    indices = {i["name"] for i in insp.get_indexes("guion_prompt")}
    assert {i.name for i in db.guion_prompt.indexes} <= indices
    assert {i.name for i in db.guion_mensaje.indexes} <= {i["name"] for i in insp.get_indexes("guion_mensaje")}
    command.downgrade(cfg, "0017")
    insp = sa.inspect(db.engine())
    assert not ({"guion_prompt", "guion_mensaje"} & set(insp.get_table_names()))
    db._reset_para_tests()
