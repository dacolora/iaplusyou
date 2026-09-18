"""Bloque 7 — publicación orgánica: tabla publicacion, canales, redacción
con Claude (fake) y fallback, publicación por plataforma con los uploaders
falsos. Sin red."""
import json
import os

import pytest
import sqlalchemy as sa

PAISES = [{"pais": "CO", "idioma": "es", "presupuesto_dia": 20000.0}]
GUION = {"bloques": [{"rol": "hook", "texto_pantalla": "¿Tus pies sufren en casa?", "texto_voz": "¿Tus pies sufren?"},
                     {"rol": "beneficio", "texto_pantalla": "", "texto_voz": "Suela de memoria que abraza."},
                     {"rol": "cta", "texto_pantalla": "Pídelas hoy", "texto_voz": "Pídelas hoy"}]}


def _pieza(db, cliente="acme", tipo="final", guion=GUION, productos_ids=("pantufla_nube",), url="https://r2/f.mp4",
           accion="camina por la casa", idioma="es"):
    with db.conectar() as con:
        ahora = db.ahora()
        cid = con.execute(db.concepto.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, origen="manual", legado_id=f"cf_{cliente}",
            idioma_base="es", extra={"productos_ids": list(productos_ids), "accion_central": accion})).inserted_primary_key[0]
        return con.execute(db.pieza.insert().values(
            cliente=cliente, creado_en=ahora, actualizado_en=ahora, concepto_id=cid, tipo=tipo, estado="listo",
            pais="CO", idioma=idioma, url_video=url, legado_id=f"cf_{cliente}__es_CO", guion=guion, extra={})).inserted_primary_key[0]


def _producto(cliente="acme", activo="pantufla_nube", url="https://tienda.co/p/pantufla-nube"):
    import tiendas
    pid = tiendas.asegurar_manual(cliente, activo, "Pantufla Nube de Algodón", "Pantufla con suela de memoria.")
    tiendas.marcar_producto(cliente, pid, url_compra=url)
    return pid


@pytest.fixture()
def proyecto(base_temporal, tmp_path, monkeypatch):
    """organico apunta a un BASE_DIR temporal (clientes/<c>/ y salidas/) y
    meta_conexion.cargar devuelve lo que el test ponga en `meta`."""
    import meta_conexion
    import organico
    monkeypatch.setattr(organico, "BASE_DIR", str(tmp_path))
    os.makedirs(tmp_path / "clientes" / "acme")
    meta = {}
    monkeypatch.setattr(meta_conexion, "cargar", lambda cliente: dict(meta) if cliente == "acme" and meta else None)
    return {"db": base_temporal, "tmp": tmp_path, "meta": meta, "organico": organico}


def _token(tmp_path, nombre):
    with open(tmp_path / "clientes" / "acme" / nombre, "w") as f:
        json.dump({"access_token": "SECRETO"}, f)


# ---------- migración ----------

def test_migracion_0009_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig9.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    command.upgrade(cfg, "head")
    insp = sa.inspect(db.engine())
    assert "publicacion" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("publicacion")}
    assert {"cliente", "pieza_id", "experimento_pieza_id", "plataforma", "estado", "caption", "titulo", "id_externo",
            "url", "error", "publicado_en", "origen", "extra"} <= cols
    indices = {i["name"] for i in insp.get_indexes("publicacion")}
    assert {"ix_publicacion_cliente_pieza", "uq_publicacion_viva"} <= indices
    db._reset_para_tests()
    command.downgrade(cfg, "0008")
    assert "publicacion" not in sa.inspect(db.engine()).get_table_names()
    db._reset_para_tests()
    command.upgrade(cfg, "head")
    assert "publicacion" in sa.inspect(db.engine()).get_table_names()
    db._reset_para_tests()


def test_indice_vivo_rechaza_duplicado_a_nivel_de_base(base_temporal):
    """El índice único parcial es la garantía atómica: dos inserts vivos de la
    misma pieza/plataforma chocan aunque se salten organico.crear."""
    db = base_temporal
    pid = _pieza(db)
    ahora = db.ahora()
    fila = dict(cliente="acme", creado_en=ahora, actualizado_en=ahora, pieza_id=pid, plataforma="facebook",
                estado="publicada", caption="x", origen="manual", extra={})
    with db.conectar() as con:
        con.execute(db.publicacion.insert().values(**fila))
    with pytest.raises(sa.exc.IntegrityError):
        with db.conectar() as con:
            con.execute(db.publicacion.insert().values(**dict(fila, estado="en_cola")))
    with db.conectar() as con:  # una en error no cuenta
        con.execute(db.publicacion.insert().values(**dict(fila, estado="error")))


# ---------- canales ----------

def test_canales_sin_nada_conectado(proyecto):
    org = proyecto["organico"]
    cs = {c["plataforma"]: c for c in org.canales("acme")}
    assert [c["plataforma"] for c in org.canales("acme")] == ["instagram", "facebook", "tiktok", "youtube"]
    assert not any(c["disponible"] for c in cs.values())
    assert cs["facebook"]["motivo"] == "Conecta Meta con una Página"
    assert cs["instagram"]["motivo"] == "Conecta Meta con una Página"
    assert cs["youtube"]["motivo"] == "Falta token_youtube.json (autoriza desde tu Mac con auth/auth_youtube.py)"
    assert cs["tiktok"]["motivo"] == "Falta token_tiktok.json (autoriza desde tu Mac con auth/auth_tiktok.py)"
    assert cs["facebook"]["nombre"] == "Facebook (Página)"
    assert org.disponibles("acme") == []


def test_canales_segun_meta_y_tokens(proyecto):
    org = proyecto["organico"]
    proyecto["meta"].update({"page_access_token": "tok", "page_id": "1"})
    cs = {c["plataforma"]: c for c in org.canales("acme")}
    assert cs["facebook"]["disponible"] and cs["facebook"]["motivo"] == ""
    assert not cs["instagram"]["disponible"]
    assert cs["instagram"]["motivo"] == "La cuenta de Instagram no está vinculada a la Página"
    proyecto["meta"]["ig_user_id"] = "9"
    _token(proyecto["tmp"], "token_youtube.json")
    cs = {c["plataforma"]: c for c in org.canales("acme")}
    assert cs["instagram"]["disponible"] and cs["youtube"]["disponible"] and not cs["tiktok"]["disponible"]
    _token(proyecto["tmp"], "token_tiktok.json")
    assert org.disponibles("acme") == ["instagram", "facebook", "tiktok", "youtube"]
    # Otro proyecto no hereda nada.
    assert org.disponibles("otro") == []


# ---------- redacción ----------

def test_redactar_con_claude_fake_aplica_reglas_por_plataforma(proyecto, monkeypatch):
    import generador_prompts
    org = proyecto["organico"]
    db = proyecto["db"]
    _producto()
    pid = _pieza(db)
    visto = {}

    def fake(contexto, plataformas):
        visto.update(contexto=contexto, plataformas=list(plataformas))
        return {p: {"titulo": "Pantufla Nube — la más suave " * 6,
                    "caption": "¿Tus pies sufren? Mira https://tienda.co/p/pantufla-nube y www.otra.com hoy. #pantufla"}
                for p in plataformas}
    monkeypatch.setattr(generador_prompts, "caption_organico", fake)

    out = org.redactar("acme", pid, ["instagram", "youtube", "tiktok", "facebook"])
    assert visto["plataformas"] == ["instagram", "youtube", "tiktok", "facebook"]
    ctx = visto["contexto"]
    assert ctx["nombre_producto"] == "Pantufla Nube de Algodón" and ctx["url_compra"] == "https://tienda.co/p/pantufla-nube"
    assert ctx["idioma"] == "es" and "hook: ¿Tus pies sufren en casa?" in ctx["guion_texto"]
    assert "beneficio: Suela de memoria que abraza." in ctx["guion_texto"]
    assert set(out) == {"instagram", "youtube", "tiktok", "facebook"}
    for p in ("instagram", "tiktok"):
        assert "http" not in out[p]["caption"] and "www." not in out[p]["caption"]
        assert "Link en bio." in out[p]["caption"]
    for p in ("facebook", "youtube"):
        assert "https://tienda.co/p/pantufla-nube" in out[p]["caption"]
        assert "Link en bio" not in out[p]["caption"]
    # Hashtags: había 1, se completan a 3 con el nombre del producto.
    for p in out:
        tags = [t for t in out[p]["caption"].split() if t.startswith("#")]
        assert 3 <= len(tags) <= 8, out[p]["caption"]
        assert "#pantufla" in tags
    assert len(out["youtube"]["titulo"]) <= 100 and len(out["tiktok"]["titulo"]) <= 150
    assert len(out["facebook"]["titulo"]) <= 150


def test_redactar_fallback_sin_claude(proyecto, monkeypatch):
    import generador_prompts
    org = proyecto["organico"]
    db = proyecto["db"]
    _producto()
    pid = _pieza(db)

    def explota(contexto, plataformas):
        raise RuntimeError("Falta ANTHROPIC_API_KEY")
    monkeypatch.setattr(generador_prompts, "caption_organico", explota)

    out = org.redactar("acme", pid, ["instagram", "facebook"])
    ig, fb = out["instagram"], out["facebook"]
    assert ig["caption"].startswith("¿Tus pies sufren en casa?")  # hook del guion
    assert "Link en bio." in ig["caption"] and "http" not in ig["caption"]
    assert "Consíguelo aquí: https://tienda.co/p/pantufla-nube" in fb["caption"]
    for t in ("#pantufla", "#nube", "#algodon"):
        assert t in ig["caption"] and t in fb["caption"]
    assert ig["titulo"] == "Pantufla Nube de Algodón"


def test_redactar_clon_sin_producto_usa_accion_central(proyecto, monkeypatch):
    """Un clon (sin guion) toma la acción central como gancho; sin producto
    en la tabla, el nombre sale de la acción y url_compra del experimento."""
    import experimentos as ex
    import generador_prompts
    org = proyecto["organico"]
    db = proyecto["db"]
    pid = _pieza(db, tipo="clon_limpio", guion=None, productos_ids=(), accion="Salta sobre la cama con las pantuflas")
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://tienda.co/ofertas", "COP")
    ex.agregar_pieza("acme", eid, pid, "CO")
    monkeypatch.setattr(generador_prompts, "caption_organico", lambda c, p: (_ for _ in ()).throw(RuntimeError("no")))
    out = org.redactar("acme", pid, ["youtube"])
    assert out["youtube"]["caption"].startswith("Salta sobre la cama con las pantuflas")
    assert "https://tienda.co/ofertas" in out["youtube"]["caption"]
    assert len(out["youtube"]["titulo"]) <= 100


def test_redactar_recorta_maximos_y_hashtags(proyecto, monkeypatch):
    import generador_prompts
    org = proyecto["organico"]
    db = proyecto["db"]
    _producto()
    pid = _pieza(db)
    largo = ("palabra " * 900).strip()  # ~7200 chars
    muchos = " ".join(f"#tag{i}" for i in range(12))
    monkeypatch.setattr(generador_prompts, "caption_organico",
                        lambda c, p: {x: {"titulo": "T" * 300, "caption": f"{largo} {muchos}"} for x in p})
    out = org.redactar("acme", pid, ["instagram", "facebook", "tiktok"])
    assert len(out["instagram"]["caption"]) <= 2200 and len(out["tiktok"]["caption"]) <= 2200
    assert len(out["facebook"]["caption"]) <= 5000
    assert len(out["tiktok"]["titulo"]) == 150 and len(out["facebook"]["titulo"]) <= 150
    tags = [t for t in out["facebook"]["caption"].split() if t.startswith("#")]
    assert len(tags) == 8 and "#tag11" not in tags
    # El recorte cae en un límite de palabra: la última palabra del cuerpo (todas
    # son "palabra" en el texto de prueba) nunca queda a medias.
    for p in ("instagram", "facebook", "tiktok"):
        cuerpo = out[p]["caption"].split("\n\n")[0]
        ultima = cuerpo.split()[-1]
        assert ultima == "palabra", (p, ultima)
    with pytest.raises(ValueError):
        org.redactar("acme", pid, ["twitter"])
    with pytest.raises(ValueError):
        org.redactar("otro", pid, ["instagram"])


def test_recortar_en_palabra_nunca_corta_a_mitad_de_palabra_ni_de_hashtag():
    import organico as org
    assert org._recortar_en_palabra("hola mundo", 20) == "hola mundo"
    assert org._recortar_en_palabra("hola mundo bonito", 8) == "hola"
    # tope=9 cae a mitad de "#mundo": se descarta entero, no queda "#mun".
    assert org._recortar_en_palabra("hola #mundo bonito", 9) == "hola"
    # tope=11 cae justo tras "#mundo" completo: se conserva.
    assert org._recortar_en_palabra("hola #mundo bonito", 11) == "hola #mundo"
    # Sin ningún espacio antes del tope no hay dónde cortar: corte duro.
    assert org._recortar_en_palabra("palabragigante", 4) == "pala"


def test_hashtags_de_excluye_numeros_puros():
    import organico as org
    tags = org._hashtags_de("Pack 100 Bolsas 2024", org.HASHTAGS_MAX)
    assert "#100" not in tags and "#2024" not in tags
    assert "#pack" in tags and "#bolsas" in tags


def test_ajustar_agrega_link_en_bio_si_hay_url_compra_aunque_el_texto_no_traiga_link():
    import organico as org
    contexto = {"nombre_producto": "Pantufla Nube", "url_compra": "https://tienda.co/p/x", "idioma": "es"}
    out = org.ajustar("instagram", None, "Un texto sin ningún link. #pantufla #nube #algo", contexto)
    assert "Link en bio." in out["caption"]
    # Sin url_compra y sin link en el texto original, no se fuerza el CTA.
    sin_url = org.ajustar("instagram", None, "Otro texto sin link. #a #b #c", {"nombre_producto": "X", "idioma": "es"})
    assert "Link en bio." not in sin_url["caption"]
    # No se duplica si el texto ya trae la frase.
    con_frase = org.ajustar("instagram", None, "Texto. Link en bio. #a #b #c", contexto)
    assert con_frase["caption"].lower().count("link en bio") == 1


def test_ajustar_traduce_link_en_bio_segun_idioma():
    import organico as org
    contexto = {"nombre_producto": "X", "url_compra": "https://t.co/x", "idioma": "en"}
    out = org.ajustar("tiktok", None, "Just a caption without any link. #a #b #c", contexto)
    assert "Link in bio." in out["caption"]


def test_ajustar_texto_larguisimo_conserva_cta_y_hashtags():
    """Un caption de 3 000 chars con URL: el recorte se come cuerpo, nunca el
    «Link en bio.» (IG/TikTok) ni la url de compra (FB/YT) ni los hashtags."""
    import organico as org
    contexto = {"nombre_producto": "Pantufla Nube", "url_compra": "https://tienda.co/p/x", "idioma": "es"}
    largo = ("palabra " * 375).strip() + " https://otra.com/q " + ("otra " * 220).strip() + " #a #b #c"
    ig = org.ajustar("instagram", None, largo, contexto)["caption"]
    assert len(ig) <= org.PLATAFORMAS["instagram"]["max_caption"]
    assert "https://" not in ig and ig.endswith("Link en bio.\n\n#a #b #c")
    fb = org.ajustar("facebook", None, ("palabra " * 700).strip() + " #a #b #c", contexto)["caption"]
    assert len(fb) <= org.PLATAFORMAS["facebook"]["max_caption"]
    assert fb.endswith("https://tienda.co/p/x\n\n#a #b #c")


def test_normalizar_captions_ajusta_todo_y_deja_pasar_lo_vacio(proyecto):
    """Important #1 (Task 3): la misma forma de entrada y salida; cada
    caption no vacío pasa por ajustar con el contexto de la pieza, las
    claves extra se conservan, las entradas sin caption y las plataformas
    desconocidas salen tal cual; pieza ajena → ValueError."""
    import pytest
    from tests.test_experimentos_db import _pieza
    org = proyecto["organico"]
    pid = _pieza(proyecto["db"])
    entrada = {"instagram": {"titulo": "", "caption": "Mira esto https://x.com/p #a #b #c", "extra": {"fallback": True}},
               "facebook": {"titulo": "T", "caption": ""},
               "twitter": {"caption": "no existe"}}
    out = org.normalizar_captions("acme", pid, entrada)
    assert set(out) == {"instagram", "facebook", "twitter"}
    assert out["instagram"]["caption"] == "Mira esto\n\nLink en bio.\n\n#a #b #c"
    assert out["instagram"]["titulo"] == f"Pieza {pid}" and out["instagram"]["extra"] == {"fallback": True}
    assert out["facebook"] == {"titulo": "T", "caption": ""} and out["twitter"] == {"caption": "no existe"}
    assert entrada["instagram"]["caption"].startswith("Mira esto https")   # no muta la entrada
    # Idempotente sobre texto ya ajustado.
    assert org.normalizar_captions("acme", pid, out)["instagram"] == out["instagram"]
    with pytest.raises(ValueError, match="no existe en este proyecto"):
        org.normalizar_captions("acme", 999999, entrada)


def test_caption_organico_arma_el_mensaje_y_parsea_json(monkeypatch):
    """La función real: arma el mensaje delimitado y parsea el JSON de Claude
    (cliente falso, sin red)."""
    import generador_prompts as gp
    llamadas = {}

    class _Bloque:
        type = "text"

        def __init__(self, t):
            self.text = t

    class _Msgs:
        def create(self, **kw):
            llamadas.update(kw)
            return type("R", (), {"content": [_Bloque('```json\n{"instagram": {"titulo": "Hola", "caption": "Texto #a"}, '
                                                        '"youtube": "mal"}\n```')]})()

    class _Cliente:
        def __init__(self, api_key=None):
            self.messages = _Msgs()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(gp.anthropic, "Anthropic", _Cliente)
    out = gp.caption_organico({"nombre_producto": "P", "descripcion": "d </descripcion> x", "url_compra": "https://t",
                               "idioma": "es", "guion_texto": "hook: h", "hashtags_base": ["#p"]}, ["instagram", "youtube"])
    assert out == {"instagram": {"titulo": "Hola", "caption": "Texto #a"}}
    msg = llamadas["messages"][0]["content"]
    assert "<descripcion>\nd  x\n</descripcion>" in msg and "url_compra: https://t" in msg and "<guion>\nhook: h\n</guion>" in msg
    assert llamadas["system"] == gp.CAPTION_ORGANICO_PROMPT
    _Msgs.create = lambda self, **kw: type("R", (), {"content": [_Bloque("no es json")]})()
    with pytest.raises(Exception):
        gp.caption_organico({"nombre_producto": "P"}, ["instagram"])


def test_redactar_registra_el_fallo_de_claude_y_marca_fallback(proyecto, monkeypatch, caplog):
    """Si Claude falla, `redactar` no lo traga en silencio: queda logueado
    (`creatv.organico`) y cada plataforma que salió por el fallback lo dice
    en `extra.fallback`."""
    import logging
    import generador_prompts
    org = proyecto["organico"]
    db = proyecto["db"]
    _producto()
    pid = _pieza(db)

    def explota(contexto, plataformas):
        raise RuntimeError("Falta ANTHROPIC_API_KEY")
    monkeypatch.setattr(generador_prompts, "caption_organico", explota)

    with caplog.at_level(logging.WARNING, logger="creatv.organico"):
        out = org.redactar("acme", pid, ["instagram", "facebook"])
    assert "creatv.organico" in caplog.text and "Claude falló" in caplog.text
    assert out["instagram"]["extra"] == {"fallback": True}
    assert out["facebook"]["extra"] == {"fallback": True}


def test_redactar_marca_fallback_solo_en_la_plataforma_que_claude_no_devolvio(proyecto, monkeypatch):
    import generador_prompts
    org = proyecto["organico"]
    db = proyecto["db"]
    _producto()
    pid = _pieza(db)

    def parcial(contexto, plataformas):
        return {"instagram": {"titulo": "T", "caption": "Texto real de Claude. #a #b #c"}}
    monkeypatch.setattr(generador_prompts, "caption_organico", parcial)

    out = org.redactar("acme", pid, ["instagram", "facebook"])
    assert out["instagram"]["extra"] == {"fallback": False}
    assert out["facebook"]["extra"] == {"fallback": True}


def test_redactar_copy_en_el_idioma_de_la_pieza(proyecto, monkeypatch):
    """Fallback y CTA salen en español/inglés/portugués según `pieza.idioma`;
    un idioma sin traducción cae a español."""
    import generador_prompts
    org = proyecto["organico"]
    db = proyecto["db"]
    _producto()

    def explota(contexto, plataformas):
        raise RuntimeError("no")
    monkeypatch.setattr(generador_prompts, "caption_organico", explota)

    pid_en = _pieza(db, idioma="en")
    out_en = org.redactar("acme", pid_en, ["instagram", "facebook"])
    assert "Link in bio." in out_en["instagram"]["caption"]
    assert "Get it here: https://tienda.co/p/pantufla-nube" in out_en["facebook"]["caption"]

    pid_pt = _pieza(db, idioma="pt")
    out_pt = org.redactar("acme", pid_pt, ["instagram", "facebook"])
    assert "Link na bio." in out_pt["instagram"]["caption"]
    assert "Garanta o seu: https://tienda.co/p/pantufla-nube" in out_pt["facebook"]["caption"]

    pid_fr = _pieza(db, idioma="fr")  # sin traducción -> español por defecto
    out_fr = org.redactar("acme", pid_fr, ["instagram"])
    assert "Link en bio." in out_fr["instagram"]["caption"]


# ---------- crear / listar ----------

def test_crear_listar_actualizar_y_duplicado(proyecto):
    org = proyecto["organico"]
    db = proyecto["db"]
    pid = _pieza(db)
    id1 = org.crear("acme", pid, "facebook", "Texto FB #a #b #c", titulo="T" * 200)
    with pytest.raises(ValueError, match="ya está publicada"):
        org.crear("acme", pid, "facebook", "otro")
    id2 = org.crear("acme", pid, "instagram", "Texto IG", origen="ganador")
    with pytest.raises(ValueError):
        org.crear("acme", pid, "twitter", "x")
    with pytest.raises(ValueError):
        org.crear("acme", pid, "youtube", "   ")
    with pytest.raises(ValueError):
        org.crear("otro", pid, "youtube", "x")  # pieza de otro proyecto
    with pytest.raises(ValueError):
        org.crear("acme", pid, "youtube", "x", origen="robot")
    with pytest.raises(ValueError):
        org.crear("acme", pid, "youtube", "x", ep_id=999)  # ep que no existe

    pubs = org.listar("acme", pieza_id=pid)
    assert [p["id"] for p in pubs] == [id1, id2]
    assert pubs[0]["estado"] == "en_cola" and pubs[0]["origen"] == "manual" and len(pubs[0]["titulo"]) == 150
    assert pubs[1]["origen"] == "ganador" and pubs[1]["nombre_plataforma"] == "Instagram Reels"
    assert org.por_pieza("acme") == {pid: pubs}
    assert org.listar("otro") == [] and org.obtener("otro", id1) is None

    assert org.actualizar("acme", id1, estado="error", error="Facebook respondió 400 access_token=SECRETO&x=1")
    assert org.obtener("acme", id1)["error"] == "Facebook respondió 400 access_token=***&x=1"
    assert not org.actualizar("otro", id1, estado="publicada")
    with pytest.raises(ValueError):
        org.actualizar("acme", id1, pieza_id=5)
    with pytest.raises(ValueError):
        org.actualizar("acme", id1, estado="volando")
    # En error ya no cuenta como viva: se puede volver a crear.
    id3 = org.crear("acme", pid, "facebook", "Reintento")
    assert id3 != id1 and [p["estado"] for p in org.listar("acme", pieza_id=pid)] == ["error", "en_cola", "en_cola"]


def test_crear_con_ep_id_valida_que_sea_esa_pieza(proyecto):
    import experimentos as ex
    org = proyecto["organico"]
    db = proyecto["db"]
    pid = _pieza(db)
    otra = _pieza(db)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    with pytest.raises(ValueError):
        org.crear("acme", otra, "facebook", "x", ep_id=ep)
    pub = org.crear("acme", pid, "facebook", "x", ep_id=ep)
    assert org.listar("acme", ep_id=ep)[0]["id"] == pub


# ---------- publicar ----------

class _RespuestaFake:
    def __init__(self, contenido=b"video"):
        self.contenido = contenido

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=1):
        yield self.contenido


def test_publicar_por_plataforma_guarda_estados_y_no_filtra_tokens(proyecto, monkeypatch):
    import experimentos as ex
    import publicador
    org = proyecto["organico"]
    db = proyecto["db"]
    pid = _pieza(db)
    eid = ex.crear("acme", "X", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    fb = org.crear("acme", pid, "facebook", "Texto FB", titulo="Título", ep_id=ep)
    yt = org.crear("acme", pid, "youtube", "Texto YT", titulo="Título YT", ep_id=ep)
    ig = org.crear("acme", pid, "instagram", "Texto IG")
    tk = org.crear("acme", pid, "tiktok", "Texto TK", titulo="T")

    descargas = []
    monkeypatch.setattr(org.requests, "get", lambda url, **kw: descargas.append((url, kw)) or _RespuestaFake())
    llamadas = []

    def fake_publicar(platform, entry, cliente, token_paths):
        llamadas.append((platform, dict(entry), cliente, dict(token_paths)))
        assert os.path.exists(entry["video_local"])  # el mp4 está mientras se publica
        if platform == "facebook":
            return "1234567890"
        if platform == "youtube":
            raise RuntimeError("YouTube respondió 401 con access_token=SECRETO123 (token vencido)")
        if platform == "instagram":
            return "17900000000000000"  # media_id numérico: sin URL
        return "v_pub.abc"  # tiktok publish_id
    monkeypatch.setattr(publicador, "_publicar_una", fake_publicar)
    etapas = []

    res = org.publicar("acme", [fb, yt, ig, tk, 999], on_etapa=etapas.append)
    assert res == {"ok": [fb, ig, tk], "error": [yt]}
    assert len(descargas) == 1 and descargas[0][0] == "https://r2/f.mp4" and descargas[0][1]["stream"] is True
    assert etapas == ["Descargando", "Publicando", "Publicando", "Publicando", "Publicando"]
    assert [l[0] for l in llamadas] == ["facebook", "youtube", "instagram", "tiktok"]
    e_fb = llamadas[0][1]
    assert e_fb["platforms"] == ["facebook"] and e_fb["title"] == "Título" and e_fb["caption"] == "Texto FB"
    assert e_fb["video_url"] == "https://r2/f.mp4"
    assert e_fb["video_local"] == os.path.join(str(proyecto["tmp"]), "salidas", "acme", "organico", f"{pid}.mp4")
    assert llamadas[0][3]["youtube"].endswith(os.path.join("clientes", "acme", "token_youtube.json"))
    assert not os.path.exists(e_fb["video_local"])  # borrado al terminar
    # TikTok no tiene campo de caption separado: `title` es el texto completo
    # de la publicación, así que recibe el caption, no el título corto.
    e_tk = llamadas[3][1]
    assert e_tk["platforms"] == ["tiktok"] and e_tk["title"] == "Texto TK" and e_tk["caption"] == "Texto TK"

    pubs = {p["id"]: p for p in org.listar("acme", pieza_id=pid)}
    assert pubs[fb]["estado"] == "publicada" and pubs[fb]["id_externo"] == "1234567890"
    assert pubs[fb]["url"] == "https://www.facebook.com/1234567890" and pubs[fb]["publicado_en"]
    assert pubs[ig]["estado"] == "publicada" and pubs[ig]["url"] is None and pubs[ig]["id_externo"] == "17900000000000000"
    assert pubs[tk]["estado"] == "publicada" and pubs[tk]["url"] is None and pubs[tk]["id_externo"] == "v_pub.abc"
    assert pubs[yt]["estado"] == "error" and pubs[yt]["publicado_en"] is None
    assert "SECRETO123" not in pubs[yt]["error"] and "access_token=***" in pubs[yt]["error"]

    evs = ex.eventos("acme", eid)
    tipos = [(e["tipo"], e["ep_id"]) for e in evs]
    assert ("publicacion", ep) in tipos and ("error", ep) in tipos
    assert not any("SECRETO123" in e["mensaje"] for e in evs)
    assert any("https://www.facebook.com/1234567890" in e["mensaje"] for e in evs)
    # Las que no eran del experimento no dejan evento.
    assert sum(1 for t, _ in tipos if t in ("publicacion", "error")) == 2

    # Ya publicada: no se vuelve a publicar; en error sí se reintenta.
    llamadas.clear()
    res = org.publicar("acme", [fb, yt])
    assert [l[0] for l in llamadas] == ["youtube"] and res == {"ok": [], "error": [yt]}


def test_publicar_sin_video_o_descarga_fallida_marca_error(proyecto, monkeypatch):
    import publicador
    org = proyecto["organico"]
    db = proyecto["db"]
    pid = _pieza(db, url=None)
    pub = org.crear("acme", pid, "facebook", "x")
    monkeypatch.setattr(publicador, "_publicar_una", lambda *a, **k: pytest.fail("no debía publicar"))
    assert org.publicar("acme", [pub]) == {"ok": [], "error": [pub]}
    assert "no tiene video" in org.obtener("acme", pub)["error"]

    pid2 = _pieza(db)
    pub2 = org.crear("acme", pid2, "facebook", "x")

    def explota(url, **kw):
        raise RuntimeError("timeout access_token=XYZ")
    monkeypatch.setattr(org.requests, "get", explota)
    assert org.publicar("acme", [pub2]) == {"ok": [], "error": [pub2]}
    err = org.obtener("acme", pub2)["error"]
    assert "No pude descargar el video" in err and "XYZ" not in err
    # Cross-tenant: ids de otro cliente se ignoran.
    assert org.publicar("otro", [pub2]) == {"ok": [], "error": []}


def test_interrumpir_pasa_publicando_a_error(proyecto):
    org = proyecto["organico"]
    pid = _pieza(proyecto["db"])
    a = org.crear("acme", pid, "facebook", "x")
    b = org.crear("acme", pid, "youtube", "x")
    org.actualizar("acme", a, estado="publicando")
    org.interrumpir("acme", [a, b])
    assert org.obtener("acme", a)["estado"] == "error" and "interrumpió" in org.obtener("acme", a)["error"]
    assert org.obtener("acme", b)["estado"] == "en_cola"


def test_url_publica():
    import organico as org
    assert org.url_publica("facebook", "12") == ("12", "https://www.facebook.com/12")
    assert org.url_publica("youtube", "abcDEF123") == ("abcDEF123", "https://youtu.be/abcDEF123")
    assert org.url_publica("instagram", "CxYz_12-ab") == ("CxYz_12-ab", "https://www.instagram.com/p/CxYz_12-ab")
    assert org.url_publica("instagram", "17900000000000000") == ("17900000000000000", None)
    assert org.url_publica("tiktok", "v_pub.1") == ("v_pub.1", None)
    assert org.url_publica("facebook", None) == (None, None)


def test_publicar_una_devuelve_el_id_del_uploader(monkeypatch):
    """Cambio aditivo en publicador: _publicar_una devuelve lo que devuelve
    cada uploader (organico lo guarda como id_externo)."""
    import publicador
    from uploaders import meta_uploader, youtube_uploader, tiktok_uploader
    monkeypatch.setattr(meta_uploader, "upload_to_facebook_page", lambda *a, **k: "fb1")
    monkeypatch.setattr(meta_uploader, "upload_to_instagram_reel", lambda *a, **k: "ig1")
    monkeypatch.setattr(youtube_uploader, "upload_video", lambda *a, **k: "yt1")
    monkeypatch.setattr(tiktok_uploader, "upload_video", lambda *a, **k: "tk1")
    entry = {"video_local": "/x.mp4", "video_url": "https://r2/x.mp4", "title": "t", "caption": "c"}
    assert publicador._publicar_una("facebook", entry, "acme", {}) == "fb1"
    assert publicador._publicar_una("instagram", entry, "acme", {}) == "ig1"
    assert publicador._publicar_una("youtube", entry, "acme", {}) == "yt1"
    assert publicador._publicar_una("tiktok", entry, "acme", {}) == "tk1"
    with pytest.raises(ValueError):
        publicador._publicar_una("twitter", entry, "acme", {})


# ---------- ganadoras sin publicar ----------

def test_ganadoras_sin_publicar(proyecto):
    import experimentos as ex
    org = proyecto["organico"]
    db = proyecto["db"]
    pid = _pieza(db)
    eid = ex.crear("acme", "Cojín", PAISES, "OUTCOME_TRAFFIC", 7, 100.0, "https://t", "COP")
    ep = ex.agregar_pieza("acme", eid, pid, "CO")
    ex.actualizar("acme", eid, estado="corriendo")
    ex.actualizar_pieza("acme", ep, veredicto="ganador")
    # Sin canales disponibles no hay dónde publicar.
    assert org.ganadoras_sin_publicar("acme") == []
    proyecto["meta"].update({"page_access_token": "tok", "page_id": "1"})
    g = org.ganadoras_sin_publicar("acme")
    assert [x["id"] for x in g] == [ep] and g[0]["experimento_id"] == eid and g[0]["experimento_nombre"] == "Cojín"
    assert g[0]["pieza_id"] == pid and g[0]["veredicto"] == "ganador"
    # Publicada en un canal NO disponible (youtube) sigue pendiente; en cola en uno disponible ya no.
    yt = org.crear("acme", pid, "youtube", "x")
    org.actualizar("acme", yt, estado="publicada")
    assert [x["id"] for x in org.ganadoras_sin_publicar("acme")] == [ep]
    fb = org.crear("acme", pid, "facebook", "x")
    assert org.ganadoras_sin_publicar("acme") == []
    org.actualizar("acme", fb, estado="error")
    assert [x["id"] for x in org.ganadoras_sin_publicar("acme")] == [ep]
    # Perdedoras y experimentos cerrados no aparecen.
    ex.actualizar_pieza("acme", ep, veredicto="perdedor")
    assert org.ganadoras_sin_publicar("acme") == []
    ex.actualizar_pieza("acme", ep, veredicto="ganador")
    ex.actualizar("acme", eid, estado="cerrado")
    assert org.ganadoras_sin_publicar("acme") == []
    assert org.ganadoras_sin_publicar("otro") == []
