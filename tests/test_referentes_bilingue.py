"""Biblioteca global de referentes en dos idiomas (spec 2026-09-26 §B7):
extra.i18n por referente, descripcion_en por familia (migración 0022),
clasificación bilingüe en una sola llamada para lo global, copycoders sin
Claude, la ficha en el idioma de quien mira y lo que va a Claude o a un
sprint en el del proyecto."""
import os

import sqlalchemy as sa

import idiomas
from tests.test_rutas_referentes import _anuncio, app  # noqa: F401  (fixture)


def test_migracion_0022_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig22.db'}")
    db._reset_para_tests()
    cfg = Config(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "alembic.ini"))
    command.upgrade(cfg, "head")
    assert "descripcion_en" in {c["name"] for c in sa.inspect(db.engine()).get_columns("referente_familia")}
    db._reset_para_tests()
    command.downgrade(cfg, "0021")
    assert "descripcion_en" not in {c["name"] for c in sa.inspect(db.engine()).get_columns("referente_familia")}
    db._reset_para_tests()


def test_copycoders_guarda_el_original_en_ingles():
    from referentes import copycoders
    fila = {"lib": "https://www.facebook.com/ads/library/?id=123", "img": "/i.jpg", "sig": "Shows the saving first.",
            "door": "joint pain", "brand": "B", "headline": "H", "stage": "TOF", "aw": "unaware", "family": "F"}
    a = copycoders.normalizar(fila, "https://copycoders.example/")
    assert a["extra"]["i18n"] == {"en": {"firma": "Shows the saving first.", "dolor": "joint pain"}}


def test_rellenar_i18n_de_lo_ya_importado_sin_claude(base_temporal):
    from referentes import datos
    viejo, _ = datos.guardar_referente(_anuncio("7", firma="Muestra el ahorro primero.", dolor="joint pain",
                                                extra={"firma_original": "Shows the saving first.", "traducida": True}))
    sin_traducir, _ = datos.guardar_referente(_anuncio("8", firma="Original only.", dolor="ninguno-oferta",
                                                       extra={"firma_original": "Original only.", "traducida": False}))
    assert datos.rellenar_i18n_copycoders() == 2
    assert datos.referente(None, viejo)["extra"]["i18n"] == {
        "en": {"firma": "Shows the saving first.", "dolor": "joint pain"}, "es": {"firma": "Muestra el ahorro primero."}}
    assert datos.referente(None, sin_traducir)["extra"]["i18n"] == {
        "en": {"firma": "Original only.", "dolor": "ninguno-oferta"}}
    assert datos.rellenar_i18n_copycoders() == 0                      # idempotente


def test_marcar_traducidas_escribe_i18n_es(base_temporal):
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio("9", firma="giant headline",
                                              extra={"firma_original": "giant headline", "traducida": False}))
    datos.marcar_traducidas([(rid, "Titular gigante")])
    assert datos.referente(None, rid)["extra"]["i18n"]["es"] == {"firma": "Titular gigante"}


def test_localizado_y_descripcion_de_familia():
    from referentes import datos
    r = {"firma": "Firma", "dolor": "dolor", "extra": {"i18n": {"en": {"firma": "Signature"}}}}
    assert datos.localizado(r, "en")["firma"] == "Signature" and datos.localizado(r, "en")["dolor"] == "dolor"
    assert datos.localizado(r, "es") is r
    f = {"descripcion": "Precio tachado.", "descripcion_en": "Struck-through price."}
    assert datos.descripcion_familia(f, "en") == "Struck-through price."
    assert datos.descripcion_familia(f, "es") == "Precio tachado."
    assert datos.descripcion_familia({"descripcion": "Precio tachado.", "descripcion_en": None}, "en") == "Precio tachado."
    assert datos.descripcion_familia(None, "en") is None


def _llamar_falso(respuesta, visto):
    def falso(content, max_tokens=4000, system=None):
        visto.update(texto=content[0]["text"], system=system)
        return respuesta, 900, 80
    return falso


def test_clasificar_global_pide_los_dos_idiomas_en_una_llamada(monkeypatch):
    from referentes import clasificar
    visto = {}
    monkeypatch.setattr(clasificar, "_llamar", _llamar_falso(
        '{"etapa": "TOF", "consciencia": "unaware", "familia": "Villain Made Visible", "familia_nueva": null, '
        '"dolor": "hinchazón", "firma": "Muestra el problema.", '
        '"traducciones": {"en": {"firma": "Shows the problem.", "dolor": "bloating"}}}', visto))
    ref = {"cliente": None, "marca": "M", "titular": "T", "cuerpo": "C", "idioma": "en",
           "imagen_url": "https://cdn.example/x.jpg"}
    assert clasificar.salida_para(ref) == ("es", "en")
    r, _, _ = clasificar.clasificar(ref, ["Villain Made Visible"])
    assert '"traducciones"' in visto["texto"] and "en español" in visto["texto"] and "en inglés" in visto["texto"]
    assert len(visto["system"]) == 1                    # sin «escribe TODO en X»: se piden dos idiomas
    assert r["firma"] == "Muestra el problema." and r["i18n"] == {
        "es": {"firma": "Muestra el problema.", "dolor": "hinchazón"},
        "en": {"firma": "Shows the problem.", "dolor": "bloating"}}


def test_clasificar_de_un_proyecto_en_ingles(monkeypatch):
    from referentes import clasificar
    visto = {}
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(clasificar, "_llamar", _llamar_falso(
        '{"etapa": "MOF", "consciencia": "problem-aware", "familia": "Villain Made Visible", "familia_nueva": null, '
        '"dolor": "bloating", "firma": "Shows the problem."}', visto))
    ref = {"cliente": "acme", "marca": "M", "titular": "T", "cuerpo": "C", "idioma": "en",
           "imagen_url": "https://cdn.example/x.jpg"}
    assert clasificar.salida_para(ref) == ("en",)
    r, _, _ = clasificar.clasificar(ref, ["Villain Made Visible"])
    assert '"traducciones"' not in visto["texto"] and "en inglés" in visto["texto"]
    s = visto["system"][1]["text"]
    assert s.startswith(idiomas.orden_idioma("en")) and s.endswith(idiomas.orden_idioma("en"))
    assert r["i18n"] == {"en": {"firma": "Shows the problem.", "dolor": "bloating"}}


def test_clasificar_uno_guarda_i18n(base_temporal, monkeypatch):
    from referentes import clasificar, datos
    from tareas import referentes as tr
    monkeypatch.setattr(clasificar, "clasificar", lambda referente, vocabulario: (
        {"etapa": "TOF", "consciencia": "unaware", "familia": "X", "familia_nueva": None, "dolor": "d", "firma": "f",
         "lead": None, "i18n": {"es": {"firma": "f", "dolor": "d"}, "en": {"firma": "f-en", "dolor": "d-en"}}}, 1, 1))
    datos.familia_asegurar("X", "")
    g, _ = datos.guardar_referente(_anuncio("1"))
    ok, _, _ = tr._clasificar_uno(None, datos.referente(None, g))
    assert ok and datos.referente(None, g)["extra"]["i18n"]["en"] == {"firma": "f-en", "dolor": "d-en"}


def test_familia_nueva_de_un_proyecto_en_ingles_va_a_descripcion_en(base_temporal, monkeypatch):
    """Fix round 1 (Important): un proyecto clasificado en inglés no debe dejar
    la descripción de una familia nueva en la columna española (la que leen
    los proyectos en español)."""
    from referentes import clasificar, datos
    from tareas import referentes as tr
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    monkeypatch.setattr(clasificar, "clasificar", lambda referente, vocabulario: (
        {"etapa": "TOF", "consciencia": "unaware", "familia": None,
         "familia_nueva": {"nombre": "New Format", "descripcion": "An English description."},
         "dolor": "d", "firma": "f", "lead": None, "i18n": {"en": {"firma": "f", "dolor": "d"}}}, 1, 1))
    g, _ = datos.guardar_referente(_anuncio("70"), cliente="acme")
    ok, _, _ = tr._clasificar_uno("acme", datos.referente("acme", g))
    assert ok
    f = next(x for x in datos.familias() if x["nombre"] == "EMERGING: New Format")
    assert f["descripcion_en"] == "An English description." and not (f["descripcion"] or "").strip()


def test_familia_nueva_global_sigue_en_descripcion(base_temporal, monkeypatch):
    """Un referente global (sale en español e inglés) sigue guardando la
    descripción de una familia nueva en español, como antes del fix."""
    from referentes import clasificar, datos
    from tareas import referentes as tr
    monkeypatch.setattr(clasificar, "clasificar", lambda referente, vocabulario: (
        {"etapa": "TOF", "consciencia": "unaware", "familia": None,
         "familia_nueva": {"nombre": "Nuevo Formato", "descripcion": "Una descripción en español."},
         "dolor": "d", "firma": "f", "lead": None, "i18n": {"es": {"firma": "f", "dolor": "d"}}}, 1, 1))
    g, _ = datos.guardar_referente(_anuncio("71"))
    ok, _, _ = tr._clasificar_uno(None, datos.referente(None, g))
    assert ok
    f = next(x for x in datos.familias() if x["nombre"] == "EMERGING: Nuevo Formato")
    assert f["descripcion"] == "Una descripción en español." and not f.get("descripcion_en")


def test_validar_normaliza_el_dolor_especial_aunque_venga_en_ingles():
    """Fix round 1 (minor): bajo la orden de idioma en inglés, Claude puede
    responder la variante en inglés del dolor especial en vez del valor
    literal que `recrear.py` compara con `startswith('ninguno-')`."""
    from referentes import clasificar
    data = {"etapa": "TOF", "consciencia": "unaware", "familia": "X", "familia_nueva": None,
            "dolor": "None-Offer", "firma": "Some signature text.",
            "traducciones": {"en": {"firma": "Some signature text in English.", "dolor": "NONE-BRAND"}}}
    r = clasificar.validar(data, ["X"], salida=("es", "en"))
    assert r["dolor"] == "ninguno-oferta" and r["i18n"]["en"]["dolor"] == "ninguno-marca"
    # El valor especial en español, tal cual, no debe alterarse.
    r2 = clasificar.validar(dict(data, dolor="ninguno-marca"), ["X"], salida=("es",))
    assert r2["dolor"] == "ninguno-marca"


def test_tarea_familias_en_por_tandas_con_gasto_de_creatv(base_temporal, monkeypatch):
    import gastos
    from referentes import copycoders, datos
    from tareas import referentes as tr
    f1 = datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    f2 = datos.familia_asegurar("Us vs Them", "Nosotros contra ellos.")
    datos.familia_asegurar("Sin descripcion", "")                      # sin descripción: no se manda
    monkeypatch.setattr(tr, "FAMILIAS_POR_LLAMADA", 1)
    llamadas = []

    def falso(texto, max_tokens):
        llamadas.append(texto)
        nombre = "Price Slash Hero" if "Price Slash Hero" in texto else "Us vs Them"
        return '{"%s": "An English line."}' % nombre, 900, 300
    monkeypatch.setattr(copycoders, "_llamar", falso)
    tr.ejecutar_familias_en({"id": 5, "payload": {}})
    assert len(llamadas) == 2 and all("en inglés" in t for t in llamadas)
    por_id = {f["id"]: f for f in datos.familias()}
    assert por_id[f1]["descripcion_en"] == por_id[f2]["descripcion_en"] == "An English line."
    assert por_id[f1]["descripcion"] == "Precio tachado en grande."          # el español no se toca
    filas = gastos.historial(datos.CLIENTE_CREATV)
    assert len(filas) == 2 and all(g["tipo"] == "otro" and g["referencia"].startswith("referentes:familias_en")
                                   for g in filas)
    assert datos.familias_sin_descripcion_en() == []


def test_boton_de_familias_en_con_precio(app, monkeypatch):
    from referentes import datos
    from tareas import referentes as tr
    datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    encolados = []
    monkeypatch.setattr(tr.trabajos, "encolar", lambda job_id, tipo, payload, **kw: encolados.append((job_id, tipo, kw)) or True)
    monkeypatch.setattr(tr.trabajos, "en_curso", lambda job_id: False)
    c = app["c"]
    html = c.get("/admin/referentes").data.decode()
    assert 'action="/admin/referentes/familias/ingles"' in html
    assert "Escribir en inglés la 1 descripción que falta ≈ US$" in html
    r = c.post("/admin/referentes/familias/ingles", headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 302 and encolados[0][:2] == ("referentes:familias:en", "referentes_familias_en")
    assert encolados[0][2]["max_intentos"] == 1


def test_editar_la_descripcion_en_ingles_a_mano(app):
    from referentes import datos
    fid = datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    app["c"].post(f"/admin/referentes/familias/{fid}", data={"descripcion": "Precio tachado.", "descripcion_en": "Struck price."},
                  headers={"Sec-Fetch-Site": "same-origin"})
    f = next(x for x in datos.familias() if x["id"] == fid)
    assert (f["descripcion"], f["descripcion_en"]) == ("Precio tachado.", "Struck price.")


def test_estimado_de_clasificacion_bilingue():
    import gastos
    assert gastos.estimar("clasificacion", n=10, bilingue=True)["usd"] == round(gastos.TARIFAS["clasificacion_bilingue"] * 10, 4)
    assert gastos.estimar("clasificacion", n=10)["usd"] == round(gastos.TARIFAS["clasificacion"] * 10, 4)


def test_ficha_en_el_idioma_de_quien_mira(app):
    from referentes import datos
    fid = datos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    datos.familia_actualizar(fid, "Precio tachado en grande.", descripcion_en="Big struck-through price.")
    rid, _ = datos.guardar_referente(_anuncio("50", extra={"i18n": {"en": {"firma": "Shows the saving first."}}}))
    datos.marcar_imagen(rid, "ok", "https://r2/referentes/50.jpg")
    c = app["c"]
    html = c.get(f"/cliente/acme/referentes/{rid}/ficha").data.decode()
    assert "Firma en español" in html and "Precio tachado en grande." in html
    idiomas.guardar_de_usuario("admin", "en")
    html = c.get(f"/cliente/acme/referentes/{rid}/ficha").data.decode()
    assert "Shows the saving first." in html and "Big struck-through price." in html
    assert "Firma en español" not in html


def test_referencia_de_biblioteca_en_el_idioma_del_proyecto(base_temporal, monkeypatch):
    from referentes import datos as rdatos
    from sprints import datos
    monkeypatch.setattr(idiomas, "de_proyecto", lambda c: "en")
    fid = rdatos.familia_asegurar("Price Slash Hero", "Precio tachado en grande.")
    rdatos.familia_actualizar(fid, "Precio tachado en grande.", descripcion_en="Big struck-through price.")
    gid, _ = rdatos.guardar_referente(_anuncio("60", extra={"i18n": {"en": {"firma": "Shows the saving first."}}}))
    rdatos.marcar_imagen(gid, "ok", "https://r2/referentes/60.jpg")
    pid = datos.crear_persona("acme", "Premium")
    sid = datos.crear_sprint("acme", "October", "2026-10-01", "2026-10-31")
    cid = datos.agregar_campana("acme", sid, pid, "espejo_led", None, 1, 0)
    a = datos.referencia("acme", datos.agregar_referencia_biblioteca("acme", cid, gid))["analisis"]
    assert a["firma"] == "Shows the saving first." and a["descripcion_familia"] == "Big struck-through price."
