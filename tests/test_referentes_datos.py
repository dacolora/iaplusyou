"""referentes.datos: único escritor de referente / referente_familia / barrido."""
import pytest
import sqlalchemy as sa


@pytest.fixture(autouse=True)
def _con_copycoders(monkeypatch):
    """Estos casos siembran la biblioteca global de copycoders y la leen desde
    un proyecto: el proyecto la trajo (desde 2026-09-28 nace apagada; el caso
    apagado vive en test_referentes_copycoders_proyecto.py)."""
    import proyectos
    monkeypatch.setattr(proyectos, "referentes_copycoders", lambda cliente: True)


def _anuncio(**extra):
    base = {"anuncio_id": "1931355470987046", "pagina_id": "110920097280290", "fuente": "copycoders",
            "marca": "Lulutox Tea", "url_anuncio": "https://www.facebook.com/ads/library/?id=1931355470987046",
            "url_marca": "https://www.facebook.com/ads/library/?view_all_page_id=110920097280290",
            "titular": "WE'RE SAYING GOODBYE", "idioma": "en", "tipo": "imagen",
            "imagen_origen": "https://cdn.tryatria.com/adfiles/m1931355470987046_x.jpeg",
            "dias": 366, "variantes": 15, "activo": True,
            "etapa": "BOF", "consciencia": "most-aware", "familia": "Price Slash Hero", "dolor": "ninguno-oferta",
            "firma": "Titular gigante estilo ruptura que fabrica urgencia.", "clasificacion": "fuente",
            "extra": {"sweep": "AUG"}}
    base.update(extra)
    return base


def test_tablas_existen_y_anuncio_id_unico(base_temporal):
    import db
    with db.conectar() as con:
        con.execute(db.barrido.insert().values(cliente=None, creado_en=db.ahora(), actualizado_en=db.ahora(),
                                               fuente="copycoders", consulta={}, tope=0, estado="en_cola", extra={}))
        con.execute(db.referente.insert().values(cliente=None, creado_en=db.ahora(), actualizado_en=db.ahora(),
                                                 anuncio_id="1", fuente="copycoders", tipo="imagen",
                                                 estado_imagen="pendiente", clasificacion="fuente", extra={}))
        with pytest.raises(sa.exc.IntegrityError):
            con.execute(db.referente.insert().values(cliente=None, creado_en=db.ahora(), actualizado_en=db.ahora(),
                                                     anuncio_id="1", fuente="atria", tipo="imagen",
                                                     estado_imagen="pendiente", clasificacion="pendiente", extra={}))


def test_familia_asegurar_no_duplica_ni_pisa_descripcion(base_temporal):
    from referentes import datos
    a = datos.familia_asegurar("Blame Transplant", "Culpa a otra cosa, no a la persona.")
    b = datos.familia_asegurar("Blame Transplant", "")
    assert a == b
    f = [x for x in datos.familias() if x["nombre"] == "Blame Transplant"][0]
    assert f["descripcion"] == "Culpa a otra cosa, no a la persona." and f["origen"] == "copycoders" and f["n"] == 0
    assert datos.familia_actualizar(a, "Nueva descripción") and datos.familias()[0]["descripcion"] == "Nueva descripción"
    with pytest.raises(datos.ErrorDatos):
        datos.familia_asegurar("   ")


def test_guardar_referente_crea_y_actualiza_sin_reasignar(base_temporal):
    from referentes import datos
    rid, creado = datos.guardar_referente(_anuncio())
    assert creado is True
    r = datos.referente("acme", rid)
    assert r["cliente"] is None and r["estado_imagen"] == "pendiente" and r["clasificacion"] == "fuente"
    assert r["familia"] == "Price Slash Hero" and r["extra"]["sweep"] == "AUG"
    # Otro barrido global encuentra el mismo anuncio: actualiza días/variantes, conserva cliente y clasificación.
    rid2, creado2 = datos.guardar_referente(_anuncio(dias=400, variantes=20, cuerpo="Copy nuevo", clasificacion="pendiente",
                                                     familia=None, etapa=None), cliente=None, barrido_id=None)
    assert rid2 == rid and creado2 is False
    r = datos.referente("acme", rid)
    assert r["dias"] == 400 and r["variantes"] == 20 and r["cuerpo"] == "Copy nuevo"
    assert r["cliente"] is None and r["clasificacion"] == "fuente" and r["familia"] == "Price Slash Hero"


def test_guardar_referente_valida(base_temporal):
    from referentes import datos
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(anuncio_id=""))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(fuente="otra"))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(imagen_origen=""))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(etapa="XXX"))
    with pytest.raises(datos.ErrorDatos):
        datos.guardar_referente(_anuncio(consciencia="dormido"))


def test_referente_privado_solo_lo_ve_su_cliente(base_temporal):
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id="777"), cliente="acme")
    assert datos.referente("acme", rid)["cliente"] == "acme"
    assert datos.referente("otro", rid) is None


def _sembrar(datos):
    ids = []
    for i, (etapa, cons, fam, dolor, marca) in enumerate([
            ("TOF", "problem-aware", "Villain Made Visible", "bloating", "Primal Queen"),
            ("TOF", "problem-aware", "Blame Transplant", "fatiga", "Neurotoned"),
            ("BOF", "most-aware", "Price Slash Hero", "ninguno-oferta", "Lulutox Tea"),
            ("MOF", "solution-aware", "Value Stack", "bloating", "Primal Queen")]):
        rid, _ = datos.guardar_referente(_anuncio(anuncio_id=str(100 + i), etapa=etapa, consciencia=cons, familia=fam,
                                                  dolor=dolor, marca=marca, titular=f"Titular {i}", dias=10 * (i + 1),
                                                  firma=f"firma {fam}"))
        datos.marcar_imagen(rid, "ok", f"https://r2/referentes/{100 + i}.jpg")
        ids.append(rid)
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id="200", titular="Sin imagen"))   # pendiente: no se lista
    ids.append(rid)
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id="300", titular="De otro", fuente="atria"), cliente="otro")
    datos.marcar_imagen(rid, "ok", "https://r2/referentes/300.jpg")
    return ids


def test_listar_filtra_pagina_y_respeta_visibilidad(base_temporal):
    from referentes import datos
    _sembrar(datos)
    todo = datos.listar("acme")
    assert todo["total"] == 4 and [r["titular"] for r in todo["items"]] == ["Titular 3", "Titular 2", "Titular 1", "Titular 0"]
    assert datos.listar("acme", {"etapa": "TOF"})["total"] == 2
    assert datos.listar("acme", {"consciencia": "most-aware"})["items"][0]["marca"] == "Lulutox Tea"
    assert datos.listar("acme", {"familia": "Value Stack"})["total"] == 1
    assert datos.listar("acme", {"dolor": "bloating"})["total"] == 2
    assert datos.listar("acme", {"marca": "Primal Queen"})["total"] == 2
    assert datos.listar("acme", {"q": "blame"})["total"] == 1          # busca en firma
    assert datos.listar("acme", {"fuente": "mios"})["total"] == 0 and datos.listar("otro", {"fuente": "mios"})["total"] == 1
    assert datos.listar("otro")["total"] == 5 and datos.listar("acme", {"fuente": "atria"})["total"] == 0
    assert datos.listar("acme", {"etapa": "XXX"})["total"] == 4          # filtro inválido = sin filtro
    p = datos.listar("acme", pagina=2, por_pagina=3)
    assert p["paginas"] == 2 and p["pagina"] == 2 and len(p["items"]) == 1
    assert datos.listar("acme", pagina=99, por_pagina=3)["pagina"] == 2


def test_opciones(base_temporal):
    from referentes import datos
    _sembrar(datos)
    o = datos.opciones("acme")
    assert o["total"] == 4 and o["familias"][0][1] == 1 and len(o["familias"]) == 4
    assert o["marcas"][0] == ("Primal Queen", 2) and ("bloating", 2) in o["dolores"] and o["fuentes"] == [("copycoders", 4)]


def test_imagenes_y_traducciones(base_temporal):
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio(extra={"firma_original": "giant headline", "traducida": False}))
    assert datos.contar_imagenes() == {"ok": 0, "pendiente": 1, "error": 0}
    assert [r["id"] for r in datos.pendientes_imagen(fuente="copycoders")] == [rid]
    assert datos.marcar_imagen(rid, "error")
    assert datos.pendientes_imagen() == [] and datos.contar_imagenes()["error"] == 1
    with pytest.raises(datos.ErrorDatos):
        datos.marcar_imagen(rid, "rara")
    assert [r["id"] for r in datos.sin_traducir()] == [rid]
    assert datos.marcar_traducidas([(rid, "Titular gigante estilo ruptura")]) == 1
    r = datos.referente("acme", rid)
    assert r["firma"] == "Titular gigante estilo ruptura" and r["extra"]["traducida"] is True and r["extra"]["firma_original"] == "giant headline"
    assert datos.sin_traducir() == []


def test_sin_traducir_es_exacto_y_no_se_salta_filas_por_orden(base_temporal):
    from referentes import datos
    ids = []
    for i in range(8):
        # Las primeras 5 (menor id) ya traducidas; con la ventana vieja
        # (limite*4 filtrado en Python) un limite=1 sólo miraba las 4
        # primeras filas y las encontraba todas traducidas, devolviendo []
        # aunque quedaran 3 filas reales sin traducir más abajo.
        rid, _ = datos.guardar_referente(_anuncio(anuncio_id=f"st-{i}", firma=f"firma {i}",
                                                  extra={"traducida": i < 5}))
        ids.append(rid)
    pendiente = datos.sin_traducir(limite=1)
    assert len(pendiente) == 1 and pendiente[0]["id"] == ids[5]
    assert [r["id"] for r in datos.sin_traducir(limite=2)] == ids[5:7]
    assert len(datos.sin_traducir(limite=100)) == 3


def test_listar_por_familia_no_devuelve_referentes_privados(base_temporal):
    from referentes import datos
    rid_global, _ = datos.guardar_referente(_anuncio(anuncio_id="fam-global", familia="Price Slash Hero",
                                                     firma="firma global"))
    datos.marcar_imagen(rid_global, "ok", "https://r2/fam-global.jpg")
    rid_privado, _ = datos.guardar_referente(_anuncio(anuncio_id="fam-privado", familia="Price Slash Hero",
                                                      firma="firma privada"), cliente="acme")
    datos.marcar_imagen(rid_privado, "ok", "https://r2/fam-privado.jpg")
    resultado = datos.listar_por_familia("Price Slash Hero")
    assert [r["id"] for r in resultado] == [rid_global]


def test_barridos(base_temporal):
    from referentes import datos
    bid = datos.crear_barrido(None, "copycoders", {"url": "https://x"}, 0, pedido_por="admin")
    b = datos.barrido(bid)
    assert b["estado"] == "en_cola" and b["cliente"] is None and b["consulta"]["url"] == "https://x"
    assert datos.actualizar_barrido(bid, estado="listo", traidos=3, nuevos=2, aviso=None)
    assert datos.barridos(None, fuente="copycoders")[0]["traidos"] == 3 and datos.barridos("acme") == []
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_barrido(bid, cliente="acme")
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_barrido(bid, estado="volando")
    with pytest.raises(datos.ErrorDatos):
        datos.crear_barrido("acme", "otra", {}, 10)


# ---- actualizar_referente / pendientes_clasificacion / pendientes_imagen(barrido_id=) ---

def _con_barrido(datos, cliente=None, fuente="atria", clasificacion="pendiente", estado_imagen="ok",
                  anuncio_id=None):
    """Crea un barrido y un referente colgado de él. `estado_imagen` se aplica
    con `marcar_imagen` después del alta porque `guardar_referente` siempre
    inserta en 'pendiente'. Devuelve (barrido_id, referente_id)."""
    bid = datos.crear_barrido(cliente, fuente, {}, 10)
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id=anuncio_id or f"bar-{bid}", fuente=fuente,
                                              clasificacion=clasificacion),
                                     cliente=cliente, barrido_id=bid)
    if estado_imagen == "ok":
        datos.marcar_imagen(rid, "ok", "https://r2/referentes/x.jpg")
    elif estado_imagen == "error":
        datos.marcar_imagen(rid, "error")
    return bid, rid


def test_actualizar_referente_columnas_permitidas(base_temporal):
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id="upd-1", etapa=None, consciencia=None, familia=None,
                                              dolor=None, firma=None, clasificacion="pendiente"))
    assert datos.actualizar_referente(rid, etapa="TOF", consciencia="unaware", familia="X",
                                      dolor="d", firma="f", clasificacion="claude")
    r = datos.referente("acme", rid)
    assert r["etapa"] == "TOF" and r["consciencia"] == "unaware" and r["familia"] == "X"
    assert r["dolor"] == "d" and r["firma"] == "f" and r["clasificacion"] == "claude"


def test_actualizar_referente_columna_no_editable_lanza():
    from referentes import datos
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_referente(1, anuncio_id="otro")


def test_actualizar_referente_clasificacion_invalida_lanza(base_temporal):
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id="upd-2"))
    with pytest.raises(datos.ErrorDatos):
        datos.actualizar_referente(rid, clasificacion="volando")


def test_pendientes_clasificacion_filtra_por_barrido(base_temporal):
    from referentes import datos
    bid1, rid1 = _con_barrido(datos, anuncio_id="pc-1")
    bid2, rid2 = _con_barrido(datos, anuncio_id="pc-2")
    pend = datos.pendientes_clasificacion(barrido_id=bid1)
    ids = [r["id"] for r in pend]
    assert rid1 in ids and rid2 not in ids


def test_pendientes_clasificacion_excluye_sin_imagen(base_temporal):
    from referentes import datos
    bid, rid = _con_barrido(datos, anuncio_id="pc-3", estado_imagen="pendiente")
    assert rid not in [r["id"] for r in datos.pendientes_clasificacion(barrido_id=bid)]


def test_pendientes_clasificacion_excluye_ya_clasificados(base_temporal):
    from referentes import datos
    bid, rid = _con_barrido(datos, anuncio_id="pc-4", clasificacion="claude", estado_imagen="ok")
    assert rid not in [r["id"] for r in datos.pendientes_clasificacion(barrido_id=bid)]


def test_pendientes_imagen_filtra_por_barrido(base_temporal):
    from referentes import datos
    bid1, rid1 = _con_barrido(datos, anuncio_id="pi-1", estado_imagen="pendiente")
    bid2, rid2 = _con_barrido(datos, anuncio_id="pi-2", estado_imagen="pendiente")
    pend = datos.pendientes_imagen(barrido_id=bid1)
    ids = [r["id"] for r in pend]
    assert rid1 in ids and rid2 not in ids


def test_pendientes_imagen_sin_filtro_sigue_funcionando_por_fuente(base_temporal):
    # Comportamiento existente (block 1, copycoders): sin barrido_id, filtra solo por fuente.
    from referentes import datos
    bid, rid = _con_barrido(datos, fuente="copycoders", anuncio_id="pi-3", estado_imagen="pendiente")
    pend = datos.pendientes_imagen(fuente="copycoders")
    assert rid in [r["id"] for r in pend]


# ---- contar_imagenes_de_barrido / reintentar_imagenes (bloque 4, tareas.referentes_barrer) ---

def test_contar_imagenes_de_barrido_no_mezcla_otros_barridos(base_temporal):
    from referentes import datos
    bid1, rid1 = _con_barrido(datos, anuncio_id="ci-1", estado_imagen="ok")
    bid2, rid2 = _con_barrido(datos, anuncio_id="ci-2", estado_imagen="pendiente")
    # Una segunda fila del MISMO barrido 2, en error: no debe contarse como ok ni pendiente,
    # pero SÍ como error (Important 1: antes el llamador leía este lugar del tuple como
    # si fuera "pendiente", que a la altura de clasificar siempre es 0 -- nunca veía los
    # errores reales).
    rid3, _ = datos.guardar_referente(_anuncio(anuncio_id="ci-3", fuente="atria"), barrido_id=bid2)
    datos.marcar_imagen(rid3, "error")
    assert datos.contar_imagenes_de_barrido(bid1) == (1, 0, 0)
    assert datos.contar_imagenes_de_barrido(bid2) == (0, 1, 1)
    assert datos.contar_imagenes_de_barrido(999999) == (0, 0, 0)


def test_reintentar_imagenes_resetea_solo_error_de_ese_barrido(base_temporal):
    from referentes import datos
    bid1, rid1 = _con_barrido(datos, anuncio_id="ri-1", estado_imagen="error")
    bid2, rid2 = _con_barrido(datos, anuncio_id="ri-2", estado_imagen="error")
    # Una fila 'ok' del mismo barrido 1: reintentar_imagenes no debe tocarla.
    rid3, _ = datos.guardar_referente(_anuncio(anuncio_id="ri-3", fuente="atria"), barrido_id=bid1)
    datos.marcar_imagen(rid3, "ok", "https://r2/referentes/ri-3.jpg")
    n = datos.reintentar_imagenes(bid1)
    assert n == 1
    assert datos.referente("acme", rid1)["estado_imagen"] == "pendiente"
    assert datos.referente("acme", rid3)["estado_imagen"] == "ok"
    assert datos.referente("acme", rid2)["estado_imagen"] == "error"  # otro barrido, no tocado


def test_familias_frecuentes_por_etapa_y_consciencia(base_temporal):
    from referentes import datos as rdatos

    def ref(n, familia, etapa="TOF", consciencia="problem-aware"):
        rid, _ = rdatos.guardar_referente({"anuncio_id": f"f{n}", "fuente": "atria", "imagen_origen": "https://o/x.jpg"})
        rdatos.marcar_imagen(rid, "ok", f"https://r2/{n}.jpg")
        rdatos.actualizar_referente(rid, etapa=etapa, consciencia=consciencia, familia=familia, clasificacion="claude")

    for n, fam in enumerate(["A", "A", "B"]):
        ref(n, fam)
    ref(10, "C", etapa="MOF")
    ref(11, "D", consciencia="unaware")
    assert rdatos.familias_frecuentes("acme", etapa="TOF", consciencia="problem-aware") == ["A", "B"]
    assert rdatos.familias_frecuentes("acme", etapa="TOF") == ["A", "B", "D"]
    assert rdatos.familias_frecuentes("acme", etapa="TOF", limite=1) == ["A"]


def test_borrar_de_barrido_quita_sus_referentes_y_las_familias_de_claude_que_quedan_vacias(base_temporal):
    """2026-09-27: tres barridos de «dolor de pies» trajeron anuncios sin
    relación (Atria sin orden por relevancia). Se borran sus referentes y las
    familias que Claude inventó solo para ellos; las de copycoders nunca."""
    import db
    from referentes import datos
    a = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "dolor de pies"}, 10)
    b = datos.crear_barrido("acme", "atria", {"modo": "palabra", "palabra": "plantillas"}, 10)
    datos.familia_asegurar("Price Slash Hero", origen="copycoders")
    datos.familia_asegurar("EMERGING: solo de A", origen="claude")
    datos.familia_asegurar("EMERGING: de A y B", origen="claude")

    def guardar(aid, fam, bid):
        rid, _ = datos.guardar_referente(_anuncio(anuncio_id=aid, fuente="atria", familia=fam, imagen_origen=f"https://cdn/{aid}.jpg"),
                                cliente="acme", barrido_id=bid)
        # Una clave histórica y dos privadas nuevas; la URL manda.
        clave = f"referentes/{aid}.jpg" if aid == "a1" else f"referentes/{aid}_r{rid}.jpg"
        datos.marcar_imagen(rid, "ok", f"https://r2/{clave}")
    for aid, fam in (("a1", "Price Slash Hero"), ("a2", "EMERGING: solo de A"), ("a3", "EMERGING: de A y B")):
        guardar(aid, fam, a)
    guardar("b1", "EMERGING: de A y B", b)
    r = datos.borrar_de_barrido(a)
    assert r["referentes"] == 3 and r["familias"] == ["EMERGING: solo de A"]
    assert sorted(r["claves_r2"]) == ["referentes/a1.jpg", "referentes/a2_r2.jpg", "referentes/a3_r3.jpg"]
    nombres = [f["nombre"] for f in datos.familias("acme")]
    assert "EMERGING: solo de A" not in nombres and "Price Slash Hero" in nombres and "EMERGING: de A y B" in nombres
    with db.conectar() as con:
        assert [f[0] for f in con.execute(sa.select(db.referente.c.anuncio_id))] == ["b1"]
    assert datos.barrido(a) is not None      # el barrido queda (historial del gasto)


def test_busqueda_y_marcas_sin_importar_tildes_ni_mayusculas(base_temporal):
    """«Élite» se encuentra escribiendo «elite», y «camara» encuentra «Cámara»:
    el lower() de SQLite no pliega tildes (ni pasa a minúscula lo que no es ASCII)."""
    from referentes import datos
    rid, _ = datos.guardar_referente(_anuncio(anuncio_id="900", marca="ÉLITE Cröcs", titular="La Cámara lenta"))
    datos.marcar_imagen(rid, "ok", "https://r2/referentes/900.jpg")
    por_marca = datos.listar("acme", {"marcas_nombres": ["élite crocs"]})
    assert [r["id"] for r in por_marca["items"]] == [rid]
    assert [r["id"] for r in datos.listar("acme", {"marcas_nombres": ["Elite Crocs"]})["items"]] == [rid]
    assert [r["id"] for r in datos.listar("acme", {"q": "camara"})["items"]] == [rid]
    assert [r["id"] for r in datos.listar("acme", {"q": "CÁMARA"})["items"]] == [rid]
    assert datos.listar("acme", {"q": "cama rota"})["total"] == 0


def test_pliegue_quita_tildes_y_mayusculas():
    import db
    assert db.pliegue("  ÉLITE Cröcs Ñandú ") == "elite crocs nandu"
    assert db.pliegue(None) == ""


def test_mismo_anuncio_en_dos_proyectos_no_se_pisa(base_temporal):
    from referentes import datos
    a, _ = datos.guardar_referente(_anuncio(dias=10, fuente="apify"), cliente="acme")
    b, creado = datos.guardar_referente(_anuncio(dias=99, fuente="apify"), cliente="otro")
    assert creado and a != b
    assert datos.referente("acme", a)["dias"] == 10
    assert datos.referente("otro", b)["dias"] == 99
    assert datos.referente("acme", b) is None
    assert datos.guardar_referente(_anuncio(dias=11, fuente="apify"), cliente="acme") == (a, False)


def test_propia_oculta_global_en_todos_los_listados(base_temporal):
    from referentes import datos as d
    global_id, _ = d.guardar_referente(_anuncio(anuncio_id='X', fuente='atria', familia='GLOBAL', marca='Global'), cliente=None)
    propia, _ = d.guardar_referente(_anuncio(anuncio_id='X', fuente='apify', familia='PROPIA', marca='Propia'), cliente='acme')
    for rid in (global_id, propia): d.marcar_imagen(rid, 'ok', f'https://r2/referentes/X_r{rid}.jpg')
    d.familia_asegurar('GLOBAL')
    d.familia_asegurar('PROPIA')
    assert [r['id'] for r in d.listar('acme')['items']] == [propia]
    assert [r['id'] for r in d.listar('otro')['items']] == [global_id]
    assert d.opciones('acme')['total'] == 1
    assert d.opciones('acme')['marcas'] == [('Propia', 1)]
    assert {f['nombre']: f['n'] for f in d.familias('acme')} == {'GLOBAL': 0, 'PROPIA': 1}
    assert d.familias_frecuentes('acme') == ['PROPIA']
    assert [r['id'] for r in d.listar('acme', filtros={'familia': 'GLOBAL'})['items']] == []
    assert d.referente('acme', global_id)['id'] == global_id


def test_guardar_mismo_anuncio_simultaneo_no_duplica(base_temporal, monkeypatch):
    from referentes import datos as d
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, BrokenBarrierError
    from types import SimpleNamespace
    ventana, juntos = Barrier(2), Barrier(2)
    original = sa.engine.Connection.execute
    def leer(self, sentencia, *a, **kw):
        r = original(self, sentencia, *a, **kw)
        if isinstance(sentencia, sa.sql.Select) and str(sentencia).startswith('SELECT referente.id,') and 'anuncio_id' in str(sentencia.whereclause):
            fila = r.first()
            if fila is None:
                try: ventana.wait(timeout=.5)
                except BrokenBarrierError: pass
            return SimpleNamespace(first=lambda: fila)
        return r
    monkeypatch.setattr(sa.engine.Connection, 'execute', leer)
    def guardar(_):
        juntos.wait(timeout=5)
        return d.guardar_referente(_anuncio(anuncio_id='simultaneo'), cliente='acme')
    with ThreadPoolExecutor(max_workers=2) as pool: resultados = list(pool.map(guardar, range(2)))
    assert resultados[0][0] == resultados[1][0]
    assert sorted(r[1] for r in resultados) == [False, True]
