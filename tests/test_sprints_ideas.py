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


def _contando(falso):
    """Adapta un `_llamar` falso (devuelve texto) a `_llamar_contando`
    (texto, tokens_entrada, tokens_salida): `ideas.proponer` cuenta tokens
    para registrar el gasto real desde la entrega 2 de Sprints."""
    return lambda content, max_tokens=700, system=None: (falso(content, max_tokens=max_tokens, system=system), 100, 50)


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
    monkeypatch.setattr(analisis, "_llamar_contando", _contando(_llamar_falso))
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


def test_otra_idea_descarta_la_vieja_solo_cuando_ya_hay_reemplazo(base_temporal, monkeypatch):
    """Ronda final F12: «Otra idea» (max_intentos=1) ya no descarta la idea
    ANTES de llamar a Claude. Mientras Claude responde la vieja sigue viva
    (aunque el prompt ya la trata como descartada, igual que antes); se
    descarta solo cuando se creó una del mismo tipo, y el evento conserva
    `reemplaza`."""
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    vieja = datos.crear_idea("acme", cid, "video", "Vieja fea", "x", estado_idea="aprobada")
    vistos = []

    def _llamar_falso(content, max_tokens=700, system=None):
        vistos.append((datos.idea("acme", vieja)["estado_idea"], content[0]["text"]))
        return json.dumps({"ideas": [dict(IDEA_V, titulo="La nueva")]})
    monkeypatch.setattr(analisis, "_llamar_contando", _contando(_llamar_falso))
    nuevas = ideas.proponer("acme", cid, reemplaza=vieja)
    assert vistos[0][0] == "aprobada"
    assert "IDEAS DESCARTADAS (evita ese camino): Vieja fea" in vistos[0][1]
    assert len(nuevas) == 1 and datos.idea("acme", vieja)["estado_idea"] == "descartada"
    evento = next(e for e in datos.eventos("acme", sid) if e["tipo"] == "ideas_propuestas")      # el más reciente
    assert evento["datos"]["reemplaza"] == vieja and evento["datos"]["cp_ids"] == nuevas


def test_otra_idea_que_falla_deja_la_vieja_como_estaba(base_temporal, monkeypatch):
    """Ronda final F12: si Claude falla (o no trae ninguna del mismo tipo), la
    idea vieja no se pierde: queda tal cual, sin nada en su lugar que la reemplace."""
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    vieja = datos.crear_idea("acme", cid, "video", "Vieja", "x", estado_idea="aprobada")

    def _revienta(content, max_tokens=700, system=None):
        raise RuntimeError("la API no respondió")
    monkeypatch.setattr(analisis, "_llamar_contando", _revienta)
    with pytest.raises(RuntimeError):
        ideas.proponer("acme", cid, reemplaza=vieja)
    assert datos.idea("acme", vieja)["estado_idea"] == "aprobada"
    monkeypatch.setattr(analisis, "_llamar_contando",
                        _contando(lambda content, max_tokens=700, system=None: json.dumps({"ideas": [IDEA_I]})))
    assert ideas.proponer("acme", cid, reemplaza=vieja) == []          # solo trajo una imagen
    assert datos.idea("acme", vieja)["estado_idea"] == "aprobada"
    with pytest.raises(datos.ErrorDatos):
        ideas.proponer("acme", cid, reemplaza=999)


def test_otra_idea_no_descarta_una_vieja_que_se_genero_mientras_claude_respondia(base_temporal, monkeypatch):
    """Re-revisión de la ronda final: mientras Claude escribe el reemplazo, la
    vieja sigue aprobada y «Generar» puede darle una sesión pagada. Descartarla
    después escondería esa pieza de Piezas, revisión y entrega: se queda viva."""
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    vieja = datos.crear_idea("acme", cid, "video", "Vieja", "x", estado_idea="aprobada")

    def _llamar_falso(content, max_tokens=700, system=None):
        assert datos.reclamar_cf("acme", vieja, "cf-pagada")        # «Generar» le dio sesión en ese rato
        return json.dumps({"ideas": [dict(IDEA_V, titulo="La nueva")]})
    monkeypatch.setattr(analisis, "_llamar_contando", _contando(_llamar_falso))
    nuevas = ideas.proponer("acme", cid, reemplaza=vieja)
    assert len(nuevas) == 1
    assert datos.idea("acme", vieja)["estado_idea"] == "aprobada"
    assert vieja in [p["id"] for p in datos.campana("acme", cid)["piezas"]]


def test_max_tokens_para_escala_con_la_cantidad_de_ideas():
    from sprints import ideas
    assert ideas.max_tokens_para(1) == 5200
    assert ideas.max_tokens_para(2) == 6400
    assert ideas.max_tokens_para(15) == 16000     # 22000 sin el tope: por encima el SDK exige streaming


def test_proponer_sin_faltantes_no_llama(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    for _ in range(2):
        datos.crear_idea("acme", cid, "video", "V", "v", estado_idea="aprobada")
    datos.crear_idea("acme", cid, "imagen", "I", "i", estado_idea="aprobada")
    monkeypatch.setattr(analisis, "_llamar_contando", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no debía llamar")))
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
    monkeypatch.setattr(analisis, "_llamar_contando", _contando(_llamar_falso))
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
    monkeypatch.setattr(analisis, "_llamar_contando", _contando(_llamar_falso))
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
    monkeypatch.setattr(analisis, "_llamar_contando",
                        _contando(lambda content, max_tokens=700, system=None: respuestas.pop(0)))
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
    monkeypatch.setattr(analisis, "_llamar_contando", _contando(_llamar_falso))
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
    monkeypatch.setattr(analisis, "_llamar_contando",
                        _contando(lambda content, max_tokens=700, system=None: respuestas.pop(0)))
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
    monkeypatch.setattr(analisis, "_llamar_contando",
                        _contando(lambda content, max_tokens=700, system=None: respuestas.pop(0)))
    creadas = ideas.proponer("acme", cid, n_videos=1, n_imagenes=1)
    assert respuestas == [] and len(creadas) == 2
    video, imagen = (datos.idea("acme", i) for i in creadas)
    assert video["titulo"] == IDEA_V["titulo"] and imagen["titulo"] == IDEA_I["titulo"]
    assert "error: mecanismo_obligatorio" in video["extra"]["angulo"]["faltantes"]


def test_los_datos_del_mercado_elegidos_mandan_en_las_ideas(base_temporal, monkeypatch):
    """Doctrina, bloque 2 (§4.3): la consciencia de la persona y la
    sofisticación del producto elegidas a mano van como fijas en los DATOS y
    reemplazan lo que responda Claude."""
    import tiendas
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    pid = datos.campana("acme", cid)["persona_id"]
    datos.actualizar_persona("acme", pid, extra={"conciencia": {"nivel": "consciente_del_problema"}})
    fila = tiendas.asegurar_manual("acme", "espejo_led", "Espejo LED")
    tiendas.anotar_extra("acme", fila, sofisticacion=4)
    contenidos = []
    idea = dict(IDEA_V, angulo=dict(ANGULO, lead="problema_solucion", mecanismo="luz LED en el borde del marco"))

    def _llamar_falso(content, max_tokens=700, system=None):
        contenidos.append(content[0]["text"])
        return json.dumps({"ideas": [idea]})
    monkeypatch.setattr(analisis, "_llamar_contando", _contando(_llamar_falso))
    creadas = ideas.proponer("acme", cid, n_videos=1, n_imagenes=0)
    assert len(contenidos) == 1
    assert "Consciencia de la persona (fija, no la cambies): consciente del problema" in contenidos[0]
    assert "Sofisticación del mercado (fija, no la cambies): 4" in contenidos[0]
    angulo = datos.idea("acme", creadas[0])["extra"]["angulo"]
    assert angulo["consciencia"] == "consciente_del_problema" and angulo["sofisticacion"] == 4


def test_sin_datos_del_mercado_claude_los_decide(base_temporal, monkeypatch):
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    ctx = ideas.contexto_campana("acme", datos.campana("acme", cid))
    assert ctx["fijos"] == {"consciencia": None, "sofisticacion": None}
    assert "CONSCIENCIA Y SOFISTICACIÓN: no elegidos: decide tú la consciencia y la sofisticación" in ideas.armar_prompt(ctx, 1, 0)


def test_la_consciencia_de_la_campana_manda_sobre_la_de_la_persona(base_temporal, monkeypatch):
    """Integración con el tablero de Sprints: la campaña tiene su propia
    consciencia (su enfoque) y es más específica que la de la persona, que
    queda como respaldo cuando la campaña no tiene."""
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    p = datos.campana("acme", cid)["persona_id"]
    persona = datos.persona("acme", p)
    datos.actualizar_persona("acme", p, extra=dict(persona.get("extra") or {},
                                                   conciencia={"nivel": "inconsciente", "origen": "manual"}))
    ctx = ideas.contexto_campana("acme", datos.campana("acme", cid))
    if not datos.campana("acme", cid).get("consciencia"):
        assert ctx["fijos"]["consciencia"] == "inconsciente"
    datos.actualizar_campana("acme", cid, consciencia="consciente_del_problema")
    ctx = ideas.contexto_campana("acme", datos.campana("acme", cid))
    assert ctx["fijos"]["consciencia"] == "consciente_del_problema"
    assert "Consciencia de la persona (fija, no la cambies): consciente del problema" in ideas.armar_prompt(ctx, 1, 0)


def test_reescribir_la_idea_desde_su_angulo(base_temporal, monkeypatch):
    """Doctrina, bloque 2 (§3.5): una llamada con la doctrina de gancho+video;
    cambia título, escena y sonido; el ángulo y el gancho no se tocan."""
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    cp = datos.crear_idea("acme", cid, "video", "Vieja", "escena vieja", sonido="viejo", gancho=ANGULO["gancho"],
                          extra={"angulo": dict(ANGULO, editado_en="t")})
    vistos = []

    def falso(content, max_tokens=700, system=None):
        vistos.append({"texto": content[0]["text"], "system": system, "max_tokens": max_tokens})
        return json.dumps({"titulo": "Nueva", "escena": "La luz del espejo revela el baño renovado.", "sonido": "agua"}), 900, 300
    monkeypatch.setattr(analisis, "_llamar_contando", falso)
    assert ideas.reescribir("acme", cp) == (900, 300)
    idea = datos.idea("acme", cp)
    assert (idea["titulo"], idea["escena"], idea["sonido"]) == ("Nueva", "La luz del espejo revela el baño renovado.", "agua")
    assert idea["gancho"] == ANGULO["gancho"] and idea["extra"]["angulo"]["promesa"] == ANGULO["promesa"]
    assert "ÁNGULO" in vistos[0]["texto"] and "IDEA ACTUAL (video): Vieja" in vistos[0]["texto"]
    assert "Propón" not in vistos[0]["texto"] and "DOCTRINA DE VENTA" in vistos[0]["system"][0]["text"]
    assert "Reescribe UNA idea" in vistos[0]["system"][1]["text"] and vistos[0]["max_tokens"] == ideas.max_tokens_para(1)


def test_reescribir_con_angulo_editado_no_contradice_los_fijos_ni_repite_su_propio_titulo(base_temporal, monkeypatch):
    """Doctrina, bloque 2 (revisión final #5): un ángulo editado a mano manda
    — no debe competir con los «datos del mercado» fijos del producto/persona
    (podrían decir otra cosa), y la propia idea no debe salir en «ideas que
    ya existen» (no tiene sentido pedirle a Claude que no se repita a sí
    misma)."""
    import tiendas
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    pid = datos.campana("acme", cid)["persona_id"]
    datos.actualizar_persona("acme", pid, extra={"conciencia": {"nivel": "consciente_del_problema"}})
    fila = tiendas.asegurar_manual("acme", "espejo_led", "Espejo LED")
    tiendas.anotar_extra("acme", fila, sofisticacion=4)
    datos.crear_idea("acme", cid, "imagen", "Otra idea viva", "escena x")
    cp = datos.crear_idea("acme", cid, "video", "Vieja", "escena vieja", sonido="viejo", gancho=ANGULO["gancho"],
                          extra={"angulo": dict(ANGULO, editado_en="2026-09-26T10:00:00")})
    vistos = []

    def falso(content, max_tokens=700, system=None):
        vistos.append(content[0]["text"])
        return json.dumps({"titulo": "Nueva", "escena": "Escena nueva", "sonido": "agua"}), 900, 300
    monkeypatch.setattr(analisis, "_llamar_contando", falso)
    ideas.reescribir("acme", cp)
    texto = vistos[0]
    antes_de_idea_actual = texto.split("IDEA ACTUAL")[0]
    assert "Otra idea viva" in antes_de_idea_actual and "Vieja" not in antes_de_idea_actual
    assert "elegidos por el cliente, no los cambies" not in texto


def test_reescribir_con_respuesta_invalida_no_toca_la_idea_y_devuelve_lo_pagado(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    cp = datos.crear_idea("acme", cid, "video", "Vieja", "escena vieja", extra={"angulo": ANGULO})
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: ("nada", 500, 40))
    with pytest.raises(ideas.AnalisisInvalido) as e:
        ideas.reescribir("acme", cp)
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (500, 40)
    assert datos.idea("acme", cp)["titulo"] == "Vieja"
    sin_angulo = datos.crear_idea("acme", cid, "video", "Sin", "x")
    with pytest.raises(datos.ErrorDatos):
        ideas.reescribir("acme", sin_angulo)


def test_reescribir_no_sobreescribe_si_generar_lote_ya_le_dio_pieza(base_temporal, monkeypatch):
    """Doctrina, bloque 2 (revisión final #3): la ruta solo checa `sin_sesion`
    al encolar; si «Generar lote» crea la sesión MIENTRAS Claude responde
    (~40 s después), escribir encima perdería la pieza ya generada. Si al
    momento de guardar la idea ya tiene sesión, no se escribe — se cuenta lo
    pagado con `IdeaConPieza`."""
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    cp = datos.crear_idea("acme", cid, "video", "Vieja", "escena vieja", sonido="viejo", gancho=ANGULO["gancho"],
                          extra={"angulo": ANGULO})

    def falso(content, max_tokens=700, system=None):
        # Mientras "Claude" responde, «Generar lote» crea la sesión de Crear.
        datos.actualizar_idea("acme", cp, cf_id="cf_de_generar_lote")
        return json.dumps({"titulo": "Nueva", "escena": "Otra escena", "sonido": "agua"}), 900, 300
    monkeypatch.setattr(analisis, "_llamar_contando", falso)
    with pytest.raises(ideas.IdeaConPieza) as e:
        ideas.reescribir("acme", cp)
    assert (e.value.tokens_entrada, e.value.tokens_salida) == (900, 300)
    idea = datos.idea("acme", cp)
    assert (idea["titulo"], idea["escena"], idea["sonido"]) == ("Vieja", "escena vieja", "viejo")


def test_reescribir_sin_sonido_en_json_mantiene_el_sonido_anterior(base_temporal, monkeypatch):
    """Doctrina, bloque 2 (review 1): si Claude omite la clave «sonido» en su JSON,
    la idea mantiene el sonido anterior; solo una clave presente (incluso vacía) lo reemplaza."""
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    cp = datos.crear_idea("acme", cid, "video", "Vieja", "escena vieja", sonido="olas",
                          extra={"angulo": ANGULO})
    def falso(content, max_tokens=700, system=None):
        # Claude responde sin la clave "sonido"
        return json.dumps({"titulo": "Nueva", "escena": "Escena nueva"}), 800, 250
    monkeypatch.setattr(analisis, "_llamar_contando", falso)
    assert ideas.reescribir("acme", cp) == (800, 250)
    idea = datos.idea("acme", cp)
    assert idea["titulo"] == "Nueva" and idea["escena"] == "Escena nueva"
    assert idea["sonido"] == "olas"  # Se mantiene el anterior


def test_las_pruebas_del_producto_van_en_los_datos_y_verifican_cifras(base_temporal, monkeypatch):
    """Doctrina, bloque 2 (§5.5): una cifra que está en una prueba real sí se puede decir."""
    import tiendas
    from doctrina import producto as dp
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    fila = tiendas.asegurar_manual("acme", "espejo_led", "Espejo LED")
    dp.agregar_prueba("acme", fila, "El 95 % de quienes lo instalan lo recomiendan", "comentarios")
    contenidos = []
    idea = dict(IDEA_V, angulo=dict(ANGULO, promesa="el 95 % lo recomienda"))

    def _llamar_falso(content, max_tokens=700, system=None):
        contenidos.append(content[0]["text"])
        return json.dumps({"ideas": [idea]})
    monkeypatch.setattr(analisis, "_llamar_contando", _contando(_llamar_falso))
    creadas = ideas.proponer("acme", cid, n_videos=1, n_imagenes=0)
    assert "Pruebas reales del producto" in contenidos[0] and "El 95 % de quienes lo instalan" in contenidos[0]
    angulo = datos.idea("acme", creadas[0])["extra"]["angulo"]
    assert not any("cifra_no_verificada" in f for f in angulo["faltantes"]) and len(contenidos) == 1


def test_armar_prompt_lleva_enfoque_mercado_marcas_y_momento(base_temporal, monkeypatch):
    from referentes import datos as rdatos
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    rdatos.familia_asegurar("Antes y después", "Muestra el cambio en dos cuadros")
    datos.actualizar_sprint("acme", sid, pais="US", idioma="en", marcas="Crocs", momento="Hot Sale")
    datos.actualizar_campana("acme", cid, consciencia="consciente_del_problema", dolor="pies fríos",
                             familias=["Antes y después"])
    ctx = ideas.contexto_campana("acme", datos.campana("acme", cid))
    p = ideas.armar_prompt(ctx, 1, 1)
    for frag in ("consciente del problema", "pies fríos", "Antes y después", "Muestra el cambio en dos cuadros",
                 "Estados Unidos", "inglés", "Crocs", "Hot Sale"):
        assert frag in p, frag
    assert "Navidad" not in p                        # el momento del sprint gana a la temporada vieja
    assert "inglés" in ideas.instrucciones(ctx) and "Todo en español." not in ideas.instrucciones(ctx)


def test_sin_momento_sigue_la_temporada_y_sin_enfoque_lo_dice(base_temporal, monkeypatch):
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    ctx = ideas.contexto_campana("acme", datos.campana("acme", cid))
    p = ideas.armar_prompt(ctx, 1, 1)
    assert "Navidad" in p and "regalos" in p and "(sin enfoque definido" in p and "MARCAS A IMITAR" in p
    assert "que va en inglés" in ideas.instrucciones(ctx)      # sprint nuevo: base en inglés


def test_proponer_cuenta_los_tokens_de_todas_las_llamadas(base_temporal, monkeypatch):
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    respuestas = ["esto no es json", json.dumps({"ideas": [dict(IDEA_V, referencias_ids=[rid]), IDEA_I]})]
    monkeypatch.setattr(analisis, "_llamar_contando",
                        lambda content, max_tokens=700, system=None: (respuestas.pop(0), 1000, 300))
    uso = {"entrada": 0, "salida": 0}
    ideas.proponer("acme", cid, 1, 1, uso=uso)
    assert uso == {"entrada": 2000, "salida": 600}          # la respuesta inválida y el reintento


def test_proponer_cuenta_los_tokens_aunque_falle(base_temporal, monkeypatch):
    import pytest
    from sprints import analisis, datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    monkeypatch.setattr(analisis, "_llamar_contando", lambda content, max_tokens=700, system=None: ("nada", 800, 200))
    uso = {"entrada": 0, "salida": 0}
    with pytest.raises(ideas.AnalisisInvalido):
        ideas.proponer("acme", cid, 1, 1, uso=uso)
    assert uso == {"entrada": 1600, "salida": 400}


def test_los_aprendizajes_del_proyecto_entran_en_los_datos_de_las_ideas(base_temporal, monkeypatch):
    """Doctrina, bloque 4 (§5): primero los del mismo producto; sin ninguno, la línea lo dice."""
    import proyectos
    from sprints import datos, ideas
    sid, cid, rid = _ctx(monkeypatch, datos)
    monkeypatch.setattr(proyectos, "aprendizajes", lambda cliente: [])
    p = ideas.armar_prompt(ideas.contexto_campana("acme", datos.campana("acme", cid)), 1, 0)
    assert "APRENDIZAJES DEL PROYECTO: ninguno todavía" in p
    monkeypatch.setattr(proyectos, "aprendizajes", lambda cliente: [
        {"texto": "Ganó en CO: «Otra cosa» para Otro producto", "producto": "Otro producto"},
        {"texto": "Perdió en MX: «¿Frío?» para Espejo LED", "producto": "Espejo LED"}])
    p = ideas.armar_prompt(ideas.contexto_campana("acme", datos.campana("acme", cid)), 1, 0)
    assert "LO QUE YA SE PROBÓ EN ESTE PROYECTO" in p
    assert p.index("Perdió en MX") < p.index("Ganó en CO")          # el del producto de la campaña primero
