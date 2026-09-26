import json

import pytest

ANGULO = {"audiencia": "quien renueva el baño y quiere que se vea de revista", "consciencia": "consciente_de_la_solucion",
          "sofisticacion": 2, "deseo": "un baño que se vea nuevo sin obra",
          "promesa": "tu baño se ve nuevo con solo cambiar el espejo", "mecanismo": None,
          "pruebas": [{"texto": "luz integrada en el marco", "fuente": "ficha"}], "lead": "promesa",
          "gancho": "El espejo que cambia tu baño entero", "faltantes": []}
IDEA_V = {"titulo": "Espejo al amanecer", "tipo": "video", "escena": "La cámara rodea el espejo redondo mientras la luz del amanecer entra por la ventana.",
          "sonido": "pájaros lejanos, brisa", "enfoque": "producto", "gancho": "Luz que despierta", "referencias_ids": [1, 999],
          "duracion_s": 9, "plataformas": ["instagram", "tiktok", "otra"], "angulo": ANGULO}
IDEA_I = {"titulo": "Detalle del marco", "tipo": "imagen", "escena": "Primer plano del marco metálico con reflejo cálido.",
          "sonido": "", "enfoque": "rarísimo", "gancho": "Detalle que enamora", "referencias_ids": [], "duracion_s": None,
          "plataformas": ["instagram"], "angulo": dict(ANGULO, gancho="Detalle que enamora")}


def test_parsear_valida_y_normaliza():
    from sprints import ideas
    salida = ideas.parsear(json.dumps({"ideas": [IDEA_V, IDEA_I, {"titulo": "sin escena", "tipo": "video"}]}),
                           referencias_ids_validos={1, 2}, duraciones=(5, 8, 10, 12))
    assert len(salida) == 2
    v, i = salida
    assert v["referencias_ids"] == [1] and v["duracion_s"] == 8 and v["plataformas"] == ["instagram", "tiktok"]
    assert i["enfoque"] == "producto" and i["duracion_s"] is None and i["sonido"] == ""
    with pytest.raises(ideas.AnalisisInvalido):
        ideas.parsear("nada", set(), (8,))
    with pytest.raises(ideas.AnalisisInvalido):
        ideas.parsear(json.dumps({"ideas": []}), set(), (8,))


def test_faltantes_descuenta_vivas():
    from sprints import ideas
    c = {"n_videos": 3, "n_imagenes": 2, "ideas": [
        {"tipo": "video", "estado_idea": "aprobada"}, {"tipo": "video", "estado_idea": "propuesta"},
        {"tipo": "video", "estado_idea": "descartada"}, {"tipo": "imagen", "estado_idea": "aprobada"}]}
    assert ideas.faltantes(c) == (1, 1)
    assert ideas.faltantes({"n_videos": 0, "n_imagenes": 1, "ideas": [{"tipo": "imagen", "estado_idea": "aprobada"}] * 3}) == (0, 0)


def _ctx(monkeypatch, datos, con_ref=True):
    import catalogo_productos, marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural, sin saturar.")
    monkeypatch.setattr(catalogo_productos, "encontrar", lambda c, pid, categoria=None: {"id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo con luz", "regla": "Idéntico."})
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Vidrios Sol")
    pid = datos.crear_persona("acme", "Cliente Premium", resumen="Busca calidad", descripcion="Renueva su casa", tono="cercano",
                              senales_visuales=["cocina moderna"])
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31", contexto="regalos", mood_visual={"paleta": ["#B3001B"], "luz": "cálida"})
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 2, 1)
    rid = None
    if con_ref:
        rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/a.jpg", descripcion="luz lateral", intencion=["iluminacion"])
        datos.actualizar_referencia("acme", rid, analisis={"resumen": "Espejo con luz lateral cálida", "paleta": ["#F2E9E4"], "movimiento": "sin movimiento"}, analisis_estado="listo")
    return sid, cid, rid


def test_armar_prompt_incluye_todo_el_contexto(base_temporal, monkeypatch):
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    datos.crear_idea("acme", cid, "video", "Ya existe", "x")
    datos.crear_idea("acme", cid, "video", "Descartada fea", "y", estado_idea="descartada")
    ctx = ideas.contexto_campana("acme", datos.campana("acme", cid))
    p = ideas.armar_prompt(ctx, 1, 1)
    for frag in ("Vidrios Sol", "Cliente Premium", "Busca calidad", "cocina moderna", "Espejo LED", "redondo con luz", "Navidad",
                 "regalos", "#B3001B", "Luz natural", f"ref {rid}", "Espejo con luz lateral cálida", "Ya existe", "Descartada fea",
                 "1 ideas de VIDEO", "1 ideas de IMAGEN"):
        assert frag in p, frag
    assert "Producto en primer plano" in p     # banco de prompts como ejemplos de estilo


def test_proponer_crea_ideas_y_reemplaza(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    respuestas = [json.dumps({"ideas": [dict(IDEA_V, referencias_ids=[rid]), IDEA_I]})]
    llamadas = []
    def _llamar_falso(content, max_tokens=700, system=None):
        llamadas.append(max_tokens)
        return respuestas.pop(0)
    monkeypatch.setattr(analisis, "_llamar", _llamar_falso)
    creadas = ideas.proponer("acme", cid)          # faltantes: 2 videos, 1 imagen → pide 2 y 1; Claude devuelve 1 y 1
    assert len(creadas) == 2
    assert llamadas == [ideas.max_tokens_para(3)]   # 2 videos + 1 imagen pedidos, un solo llamado (sin reintento)
    lista = datos.ideas("acme", cid)
    assert lista[0]["titulo"] == "Espejo al amanecer" and lista[0]["referencias_ids"] == [rid] and lista[0]["duracion_s"] == 8.0
    assert lista[1]["tipo"] == "imagen" and lista[1]["enfoque"] == "producto"
    respuestas.append(json.dumps({"ideas": [dict(IDEA_V, titulo="Otra versión")]}))
    nuevas = ideas.proponer("acme", cid, reemplaza=lista[0]["id"])
    assert len(nuevas) == 1
    assert datos.idea("acme", lista[0]["id"])["estado_idea"] == "descartada"
    assert datos.idea("acme", nuevas[0])["titulo"] == "Otra versión" and datos.idea("acme", nuevas[0])["tipo"] == "video"
    assert any(e["tipo"] == "ideas_propuestas" for e in datos.eventos("acme", sid))


def test_max_tokens_para_escala_con_la_cantidad_de_ideas():
    from sprints import ideas
    assert ideas.max_tokens_para(1) == 1400
    assert ideas.max_tokens_para(35) == 15000
    assert ideas.max_tokens_para(40) == 16000     # 17000 sin el tope: por encima el SDK exige streaming


def test_proponer_sin_faltantes_no_llama(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    for _ in range(2):
        datos.crear_idea("acme", cid, "video", "V", "v", estado_idea="aprobada")
    datos.crear_idea("acme", cid, "imagen", "I", "i", estado_idea="aprobada")
    monkeypatch.setattr(analisis, "_llamar", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía llamar")))
    assert ideas.proponer("acme", cid) == []
    with pytest.raises(datos.ErrorDatos):
        ideas.proponer("acme", 999)


def test_referencias_texto_describe_biblioteca_con_familia_y_etapa():
    from sprints import ideas
    refs = [{
        "id": 1, "tipo": "imagen", "origen": "biblioteca", "descripcion": "", "intencion": ["formato"],
        "analisis": {"familia": "ugc_testimonial", "descripcion_familia": "Testimonio grabado con el celular",
                     "etapa": "TOF", "dolor": "no confía en la marca", "firma": "Antes/después con el mismo encuadre",
                     "resumen": "Antes/después con el mismo encuadre"},
    }]
    texto = ideas._referencias_texto(refs)
    assert "Formato: ugc_testimonial" in texto
    assert "Testimonio grabado con el celular" in texto
    assert "funciona porque: Antes/después con el mismo encuadre" in texto
    assert "dolor: no confía en la marca" in texto
    assert "etapa: TOF" in texto


def test_sprints_nunca_usa_el_enfoque_solo_texto(base_temporal, monkeypatch):
    """«libre» (Crear sin referencias ni producto) no es un enfoque de
    campaña: ni se le ofrece a Claude ni se acepta si lo devuelve."""
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    p = ideas.instrucciones(ideas.contexto_campana("acme", datos.campana("acme", cid)))
    assert '"libre"' not in p and '"producto"' in p
    (i,) = ideas.parsear(json.dumps({"ideas": [dict(IDEA_V, enfoque="libre")]}), set(), (8,))
    assert i["enfoque"] == "producto"


def test_parsear_valida_el_angulo_y_lo_marca_con_su_origen():
    from sprints import ideas
    mala = dict(IDEA_V, angulo=dict(ANGULO, sofisticacion=4, mecanismo=None))
    sin = {k: v for k, v in IDEA_I.items() if k != "angulo"}
    buena, con_error, sin_angulo = ideas.parsear(json.dumps({"ideas": [IDEA_V, mala, sin]}), set(), (8,), "Espejo LED redondo")
    assert buena["angulo"]["origen"] == "ideas" and buena["errores_angulo"] == [] and buena["gancho"] == ANGULO["gancho"]
    assert "mecanismo_obligatorio" in con_error["errores_angulo"]
    assert "campo_faltante:promesa" in sin_angulo["errores_angulo"] and sin_angulo["gancho"] == "Detalle que enamora"


def test_armar_prompt_lleva_consciencia_embudo_precio_y_arranques(base_temporal, monkeypatch):
    import catalogo_productos, marca, proyectos, tiendas
    from sprints import datos, ideas
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "")
    monkeypatch.setattr(catalogo_productos, "encontrar",
                        lambda c, pid, categoria=None: {"id": "espejo_led", "nombre": "Espejo LED", "descripcion": "redondo con luz"})
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Vidrios Sol")
    pid_prod = tiendas.asegurar_manual("acme", "espejo_led", "Espejo LED", "redondo con luz")
    tiendas.marcar_producto("acme", pid_prod, precio=89900, moneda="COP", url_compra="https://tienda.co/espejo")
    pid = datos.crear_persona("acme", "La que renueva", resumen="Renueva el baño", extra={
        "conciencia": {"nivel": "consciente_del_problema", "detalle": "sabe que su espejo se ve viejo"},
        "encaje_producto": "le da un baño de hotel sin obra",
        "evidencia": [{"comentario_id": 1, "cita": "mi baño parece de los noventa"}]})
    tid = datos.crear_temporada("acme", "Navidad", "2026-11-15", "2026-12-31")
    sid = datos.crear_sprint("acme", "Octubre", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", tid, 1, 0, funnel="mof")
    rid = datos.agregar_referencia("acme", cid, "imagen", "https://r2/b.jpg", origen="biblioteca", descripcion="firma")
    datos.actualizar_referencia("acme", rid, analisis={"familia": "Before/After", "consciencia": "problem-aware",
                                                       "lead": "problema_solucion", "firma": "Muestra el antes"},
                                analisis_estado="listo")
    p = ideas.armar_prompt(ideas.contexto_campana("acme", datos.campana("acme", cid)), 1, 0)
    for frag in ("consciente del problema", "sabe que su espejo se ve viejo", "le da un baño de hotel sin obra",
                 "«mi baño parece de los noventa»", "MOF", "Precio: 89900 COP", "https://tienda.co/espejo",
                 "consciencia: consciente del problema", "arranque: problema-solución"):
        assert frag in p, frag


def test_proponer_guarda_el_angulo_y_manda_la_doctrina(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    vistos = []

    def _llamar_falso(content, max_tokens=700, system=None):
        vistos.append(system)
        return json.dumps({"ideas": [IDEA_V, IDEA_I]})
    monkeypatch.setattr(analisis, "_llamar", _llamar_falso)
    creadas = ideas.proponer("acme", cid, n_videos=1, n_imagenes=1)
    assert len(vistos) == 1
    assert vistos[0][0]["cache_control"] == {"type": "ephemeral"} and "DOCTRINA DE VENTA" in vistos[0][0]["text"]
    assert "Ángulo" in vistos[0][0]["text"] and "Gancho" in vistos[0][0]["text"] and '"angulo"' in vistos[0][1]["text"]
    idea = datos.idea("acme", creadas[0])
    assert idea["extra"]["angulo"]["promesa"] == ANGULO["promesa"] and idea["extra"]["angulo"]["origen"] == "ideas"
    assert idea["gancho"] == ANGULO["gancho"]


def test_proponer_pide_una_correccion_si_el_angulo_no_cumple(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    mala = dict(IDEA_V, angulo=dict(ANGULO, sofisticacion=4, mecanismo=None))
    buena = dict(IDEA_V, angulo=dict(ANGULO, sofisticacion=4, mecanismo="luz LED en el borde del marco"))
    respuestas = [json.dumps({"ideas": [mala]}), json.dumps({"ideas": [buena]})]
    contenidos = []

    def _llamar_falso(content, max_tokens=700, system=None):
        contenidos.append(content)
        return respuestas.pop(0)
    monkeypatch.setattr(analisis, "_llamar", _llamar_falso)
    creadas = ideas.proponer("acme", cid, n_videos=1, n_imagenes=0)
    assert len(contenidos) == 2 and "mecanismo_obligatorio" in contenidos[1][-1]["text"]
    ang = datos.idea("acme", creadas[0])["extra"]["angulo"]
    assert ang["mecanismo"] == "luz LED en el borde del marco"
    assert not any(f.startswith("error:") for f in ang["faltantes"])


def test_proponer_guarda_con_el_error_anotado_si_la_correccion_tampoco_cumple(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    inventada = dict(IDEA_V, angulo=dict(ANGULO, promesa="47 % más luz en tu baño"))
    respuestas = [json.dumps({"ideas": [inventada]}), json.dumps({"ideas": [inventada]})]
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700, system=None: respuestas.pop(0))
    creadas = ideas.proponer("acme", cid, n_videos=1, n_imagenes=0)
    assert len(creadas) == 1 and respuestas == []
    ang = datos.idea("acme", creadas[0])["extra"]["angulo"]
    assert any(f.startswith("error: cifra_no_verificada:47") for f in ang["faltantes"])


def test_proponer_guarda_la_primera_respuesta_si_la_correccion_falla_por_algo_ajeno(base_temporal, monkeypatch):
    """Spec §5.1: si la corrección falla (API caída, red, lo que sea — no solo
    JSON inválido), lo primero que Claude respondió (ya pagado y válido salvo
    el ángulo) no se pierde: se guarda con el error anotado en `faltantes`."""
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    mala = dict(IDEA_V, angulo=dict(ANGULO, sofisticacion=4, mecanismo=None))
    llamadas = []

    def _llamar_falso(content, max_tokens=700, system=None):
        llamadas.append(content)
        if len(llamadas) == 1:
            return json.dumps({"ideas": [mala]})
        raise RuntimeError("api caída")
    monkeypatch.setattr(analisis, "_llamar", _llamar_falso)
    creadas = ideas.proponer("acme", cid, n_videos=1, n_imagenes=0)
    assert len(llamadas) == 2 and len(creadas) == 1
    ang = datos.idea("acme", creadas[0])["extra"]["angulo"]
    assert any(f.startswith("error: mecanismo_obligatorio") for f in ang["faltantes"])


def test_proponer_con_cinco_faltantes_y_varios_errores_no_pierde_ningun_error(base_temporal, monkeypatch):
    """Fix 2: con 5 faltantes de Claude y 6 errores, el viejo `[:8]` cortaba
    el `error: cifra_no_verificada` (va último) y el ángulo quedaba sin
    marcador. Los errores van primero y ninguno se cae."""
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    mala = dict(IDEA_V, angulo=dict(ANGULO, consciencia="dormido", lead="grito", gancho=" ".join(["palabra"] * 13),
                                    promesa="47 % más luz en tu baño", faltantes=[f"falta {n}" for n in range(5)]))
    respuestas = [json.dumps({"ideas": [mala]}), json.dumps({"ideas": [mala]})]
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700, system=None: respuestas.pop(0))
    creadas = ideas.proponer("acme", cid, n_videos=1, n_imagenes=0)
    faltantes = datos.idea("acme", creadas[0])["extra"]["angulo"]["faltantes"]
    errores = [f for f in faltantes if f.startswith("error: ")]
    assert len(errores) == 6 and faltantes[:6] == errores
    assert any(f.startswith("error: cifra_no_verificada:47") for f in errores)
    assert "error: gancho_largo" in errores


def test_armar_prompt_muestra_los_precios_grandes_enteros_nunca_en_notacion_cientifica(base_temporal, monkeypatch):
    """Fix 4: `:g` escribía 1299000 como «1.299e+06» en los DATOS (y Claude
    no podía citarlo, ni el verificador reconocerlo)."""
    import tiendas
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    pid = tiendas.asegurar_manual("acme", "espejo_led", "Espejo LED", "redondo con luz")
    tiendas.marcar_producto("acme", pid, precio=1299000, moneda="COP")
    p = ideas.armar_prompt(ideas.contexto_campana("acme", datos.campana("acme", cid)), 1, 0)
    assert "Precio: 1299000 COP" in p and "e+" not in p
    tiendas.marcar_producto("acme", pid, precio=89.9, moneda="USD")
    p = ideas.armar_prompt(ideas.contexto_campana("acme", datos.campana("acme", cid)), 1, 0)
    assert "Precio: 89.90 USD" in p


def test_proponer_una_correccion_con_menos_ideas_no_reemplaza_a_la_primera(base_temporal, monkeypatch):
    """Spec §5.1: si la corrección del ángulo trae MENOS ideas que la primera
    respuesta, se quedan las de la primera (ya pagadas), con su error anotado."""
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    mala = dict(IDEA_V, angulo=dict(ANGULO, sofisticacion=4, mecanismo=None))
    buena = dict(IDEA_V, titulo="Corregida", angulo=dict(ANGULO, sofisticacion=4, mecanismo="luz LED en el borde"))
    respuestas = [json.dumps({"ideas": [mala, IDEA_I]}), json.dumps({"ideas": [buena]})]
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700, system=None: respuestas.pop(0))
    creadas = ideas.proponer("acme", cid, n_videos=1, n_imagenes=1)
    assert respuestas == [] and len(creadas) == 2
    video, imagen = (datos.idea("acme", i) for i in creadas)
    assert video["titulo"] == IDEA_V["titulo"] and imagen["titulo"] == IDEA_I["titulo"]
    assert "error: mecanismo_obligatorio" in video["extra"]["angulo"]["faltantes"]
