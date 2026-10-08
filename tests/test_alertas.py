# tests/test_alertas.py
"""Núcleo de alertas.py (spec 2026-09-20-alertas-design.md §3 y §12): el
modelo, el orden, los descartes y quién ve qué. Las fuentes reales llegan en
otras pruebas; aquí `FUENTES` se reemplaza por fuentes falsas."""
import hashlib
import re
import threading

import pytest
import sqlalchemy as sa

AHORA = "2026-10-02T10:00:00"


@pytest.fixture()
def alertas(base_temporal):
    import alertas as mod
    return mod


def _al(alertas, clave, nivel="info", grupo="faltantes", huella_="", solo_admin=False, titulo="T", detalle="D"):
    return alertas._alerta(clave, alertas.huella(huella_), nivel, grupo, titulo, detalle, "settings",
                           solo_admin=solo_admin)


def _fuente(*lista):
    return lambda cliente, ahora: list(lista)


def _rota(excepcion):
    def fn(cliente, ahora):
        raise excepcion
    return fn


def _claves(lista):
    return [a["clave"] for a in lista]


# ---------- huella y constructor ----------

def test_huella_es_determinista_y_sin_partes_es_una_constante(alertas):
    assert alertas.huella("a", 1, None) == alertas.huella("a", 1, None)
    assert alertas.huella("a", 1) != alertas.huella("a", 2)
    assert alertas.huella("a", "b") != alertas.huella("ab")
    assert alertas.huella() == hashlib.sha256(b"").hexdigest()
    assert alertas.huella("x", 2) == hashlib.sha256(b"x|2").hexdigest()
    assert re.match(alertas.HUELLA_VALIDA, alertas.huella("lo que sea"))


def test_alerta_arma_el_dict_completo_y_rechaza_nivel_o_grupo_invalidos(alertas):
    a = alertas._alerta("llave:meta", alertas.huella(), "bloquea", "puesta_a_punto", "Titulo", "Detalle", "settings")
    assert a == {"clave": "llave:meta", "huella": alertas.huella(), "nivel": "bloquea", "grupo": "puesta_a_punto",
                 "titulo": "Titulo", "detalle": "Detalle", "tab": "settings", "ancla": None, "url": None,
                 "entidad": None, "solo_admin": False}
    b = alertas._alerta("x:y", alertas.huella(), "info", "fallos", "t", "d", "nicho", ancla="a", url="?x=1",
                        entidad="7", solo_admin=True)
    assert (b["ancla"], b["url"], b["entidad"], b["solo_admin"]) == ("a", "?x=1", "7", True)
    with pytest.raises(ValueError):
        alertas._alerta("x:y", alertas.huella(), "grave", "fallos", "t", "d", "nicho")
    with pytest.raises(ValueError):
        alertas._alerta("x:y", alertas.huella(), "info", "otros", "t", "d", "nicho")


def test_las_claves_y_huellas_validas(alertas):
    ok = ["llave:wavespeed", "tablero:meta_rota:-", "nicho:error:12", "cuenta:correo:ana.perez-1", "saldo:wavespeed"]
    mal = ["sinclave", "Llave:x", "llave:", "llave:con espacio", "llave:" + "a" * 181, "../../x:y", ""]
    assert all(re.match(alertas.CLAVE_VALIDA, c) for c in ok)
    assert not any(re.match(alertas.CLAVE_VALIDA, c) for c in mal)
    assert re.match(alertas.HUELLA_VALIDA, "a" * 64)
    assert not re.match(alertas.HUELLA_VALIDA, "A" * 64)
    assert not re.match(alertas.HUELLA_VALIDA, "a" * 63)


def test_los_nombres_cubren_todos_los_grupos_niveles_y_pestañas(alertas):
    assert set(alertas.NOMBRES_GRUPO) == set(alertas.GRUPOS)
    assert set(alertas.NOMBRES_NIVEL) == set(alertas.NIVELES)
    assert {"settings", "catalogo", "creativeflowplus", "experimentos", "sprints", "nicho"} <= set(alertas.NOMBRES_TAB)
    assert isinstance(alertas.FUENTES, list)
    assert all(isinstance(n, str) and callable(fn) for n, fn in alertas.FUENTES)


# ---------- calcular ----------

def test_calcular_ordena_por_grupo_luego_nivel_y_luego_por_fuente(alertas, monkeypatch):
    monkeypatch.setattr(alertas, "FUENTES", [
        ("uno", _fuente(_al(alertas, "uno:a", "info", "fallos"), _al(alertas, "uno:b", "bloquea", "faltantes"))),
        ("dos", _fuente(_al(alertas, "dos:a", "bloquea", "fallos"), _al(alertas, "dos:b", "info", "puesta_a_punto"),
                        _al(alertas, "dos:c", "info", "faltantes"))),
        ("tres", _fuente(_al(alertas, "tres:a", "bloquea", "faltantes"), _al(alertas, "tres:b", "atencion", "faltantes"),
                         _al(alertas, "tres:c", "atencion", "decision"))),
    ])
    assert _claves(alertas.calcular("acme", AHORA)) == [
        "dos:b",                              # puesta_a_punto
        "uno:b", "tres:a", "tres:b", "dos:c",  # faltantes: bloquea (orden de fuente), atención, info
        "tres:c",                             # decision
        "dos:a", "uno:a",                     # fallos: bloquea, info
    ]


def test_calcular_pasa_el_cliente_y_la_hora_a_cada_fuente(alertas, monkeypatch):
    vistos = []

    def fuente(cliente, ahora):
        vistos.append((cliente, ahora))
        return []
    monkeypatch.setattr(alertas, "FUENTES", [("x", fuente)])
    alertas.calcular("acme", AHORA)
    alertas.calcular("otro")
    assert vistos[0] == ("acme", AHORA)
    assert vistos[1][0] == "otro" and re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", vistos[1][1])


def test_una_fuente_rota_da_una_alerta_de_revision_sin_el_mensaje_y_las_demas_siguen(alertas, monkeypatch):
    monkeypatch.setattr(alertas, "FUENTES", [
        ("buena", _fuente(_al(alertas, "buena:a", "bloquea", "faltantes"))),
        ("rota", _rota(KeyError("tok_secreto"))),
        ("otra", _fuente(_al(alertas, "otra:a", "info", "fallos"))),
    ])
    todas = alertas.calcular("acme", AHORA)
    assert _claves(todas) == ["revision:rota", "buena:a", "otra:a"]   # revision va en puesta_a_punto
    rev = todas[0]
    assert (rev["nivel"], rev["grupo"], rev["solo_admin"]) == ("info", "puesta_a_punto", True)
    assert "KeyError" in rev["detalle"]
    assert "tok_secreto" not in rev["detalle"] and "tok_secreto" not in rev["titulo"]
    assert "tok_secreto" not in repr(todas)
    assert "rota" in rev["titulo"]
    assert rev["huella"] == alertas.huella("KeyError")


def test_el_texto_de_la_alerta_de_revision_sale_en_el_idioma_de_quien_mira(alertas, monkeypatch):
    import idiomas
    monkeypatch.setattr(alertas, "FUENTES", [("rota", _rota(ValueError("x")))])
    en_espanol = alertas.calcular("acme", AHORA)[0]
    assert en_espanol["titulo"] == "No se pudo revisar rota"
    with idiomas.en_idioma("en"):
        en_ingles = alertas.calcular("acme", AHORA)[0]
    assert en_ingles["titulo"] != en_espanol["titulo"] and "rota" in en_ingles["titulo"]
    assert "ValueError" in en_ingles["detalle"] and en_ingles["detalle"] != en_espanol["detalle"]


def test_limpio_quita_tokens_y_recorta(alertas):
    assert "SECRETO" not in alertas._limpio("falló ?access_token=SECRETO&x=1")
    assert alertas._limpio("x" * 500) == "x" * 200
    assert alertas._limpio(None) == ""


def test_minutos_entre_dos_iso_o_none_si_no_se_lee(alertas):
    assert alertas._minutos("2026-10-02T09:30:00", "2026-10-02T10:00:00") == 30
    assert alertas._minutos("2026-10-02T09:30:00.123", "2026-10-02T10:00:00+00:00") == 30
    assert alertas._minutos(None, AHORA) is None
    assert alertas._minutos("ayer", AHORA) is None


def test_resumen_cuenta_por_nivel(alertas):
    lista = [_al(alertas, "a:1", "bloquea"), _al(alertas, "a:2", "info"), _al(alertas, "a:3", "info")]
    assert alertas.resumen(lista) == {"n": 3, "bloquea": 1, "atencion": 0, "info": 2}
    assert alertas.resumen([]) == {"n": 0, "bloquea": 0, "atencion": 0, "info": 0}


# ---------- descartes ----------

def _con(alertas, monkeypatch, *lista):
    monkeypatch.setattr(alertas, "FUENTES", [("f", _fuente(*lista))])


def test_descartar_oculta_la_misma_clave_y_huella_y_la_muestra_con_otra_huella(alertas, monkeypatch):
    a = _al(alertas, "faltante:logo", "atencion", huella_="v1")
    _con(alertas, monkeypatch, a)
    v = alertas.visibles("acme", AHORA)
    assert _claves(v["visibles"]) == ["faltante:logo"] and v["descartadas"] == []
    alertas.descartar("acme", "faltante:logo", a["huella"])
    v = alertas.visibles("acme", AHORA)
    assert v["visibles"] == [] and _claves(v["descartadas"]) == ["faltante:logo"]
    assert v["descartadas"][0]["descartada_en"]                      # para el desplegable «Descartadas»
    assert v["resumen"] == {"n": 0, "bloquea": 0, "atencion": 0, "info": 0}
    # la situación cambió: otra huella → vuelve a verse
    _con(alertas, monkeypatch, _al(alertas, "faltante:logo", "atencion", huella_="v2"))
    v = alertas.visibles("acme", AHORA)
    assert _claves(v["visibles"]) == ["faltante:logo"] and v["descartadas"] == []
    assert v["resumen"]["atencion"] == 1


def test_descartar_dos_veces_reemplaza_el_descarte_en_una_sola_fila(alertas):
    t = alertas.db.alerta_descartada
    alertas.descartar("acme", "faltante:logo", alertas.huella("v1"))
    alertas.descartar("acme", "faltante:logo", alertas.huella("v2"))
    with alertas.db.conectar() as con:
        filas = con.execute(sa.select(t.c.huella)).all()
    assert [f.huella for f in filas] == [alertas.huella("v2")]


def test_restaurar_vuelve_a_mostrarla(alertas, monkeypatch):
    a = _al(alertas, "faltante:logo", "atencion", huella_="v1")
    _con(alertas, monkeypatch, a)
    alertas.descartar("acme", a["clave"], a["huella"])
    assert alertas.visibles("acme", AHORA)["visibles"] == []
    alertas.restaurar("acme", a["clave"])
    v = alertas.visibles("acme", AHORA)
    assert _claves(v["visibles"]) == ["faltante:logo"] and v["descartadas"] == []
    alertas.restaurar("acme", a["clave"])                              # restaurar lo que no está no falla


def test_los_descartes_son_de_cada_proyecto(alertas, monkeypatch):
    a = _al(alertas, "faltante:logo", "atencion")
    _con(alertas, monkeypatch, a)
    alertas.descartar("acme", a["clave"], a["huella"])
    assert alertas.visibles("acme", AHORA)["visibles"] == []
    assert _claves(alertas.visibles("otro", AHORA)["visibles"]) == ["faltante:logo"]
    alertas.restaurar("otro", a["clave"])                              # no toca el de acme
    assert alertas.visibles("acme", AHORA)["visibles"] == []


def test_los_descartes_huerfanos_se_podan_y_el_faltante_vuelve_si_reaparece(alertas, monkeypatch):
    a = _al(alertas, "faltante:logo", "atencion")                     # huella vacía: una constante
    b = _al(alertas, "faltante:precio", "atencion")
    _con(alertas, monkeypatch, a, b)
    alertas.descartar("acme", a["clave"], a["huella"])
    alertas.descartar("acme", b["clave"], b["huella"])
    alertas.descartar("otro", a["clave"], a["huella"])
    _con(alertas, monkeypatch, b)                                     # el logo se resolvió
    v = alertas.visibles("acme", AHORA)
    assert v["visibles"] == [] and _claves(v["descartadas"]) == ["faltante:precio"]
    t = alertas.db.alerta_descartada
    with alertas.db.conectar() as con:
        filas = {(f.cliente, f.clave) for f in con.execute(sa.select(t.c.cliente, t.c.clave))}
    assert filas == {("acme", "faltante:precio"), ("otro", "faltante:logo")}   # solo podó el de acme
    _con(alertas, monkeypatch, a, b)                                  # meses después reaparece
    assert _claves(alertas.visibles("acme", AHORA)["visibles"]) == ["faltante:logo"]


def test_no_se_poda_en_una_pasada_con_una_fuente_caida(alertas, monkeypatch):
    a = _al(alertas, "faltante:logo", "atencion")
    monkeypatch.setattr(alertas, "FUENTES", [("f", _fuente(a))])
    alertas.descartar("acme", a["clave"], a["huella"])
    monkeypatch.setattr(alertas, "FUENTES", [("f", _rota(RuntimeError("boom")))])   # la fuente cae: la alerta «falta»
    v = alertas.visibles("acme", AHORA)
    assert _claves(v["visibles"]) == []                                # el cliente no ve la revisión (solo admin)
    assert _claves(alertas.visibles("acme", AHORA, rol="admin")["visibles"]) == ["revision:f"]
    monkeypatch.setattr(alertas, "FUENTES", [("f", _fuente(a))])      # se recupera: el descarte sigue ahí
    assert alertas.visibles("acme", AHORA)["visibles"] == []


def test_la_poda_solo_borra_lo_que_leyo(alertas, monkeypatch):
    """Si entre la lectura y el borrado otro proceso reescribe el descarte
    (otra huella), la poda no se lo lleva por delante."""
    _con(alertas, monkeypatch)                                         # ninguna alerta: todo descarte es huérfano
    alertas.descartar("acme", "faltante:logo", alertas.huella("v1"))
    original = alertas._descartes

    def descartes_y_carrera(cliente):
        filas = original(cliente)
        alertas.descartar(cliente, "faltante:logo", alertas.huella("v2"))   # otro proceso reescribe tras la lectura
        return filas
    monkeypatch.setattr(alertas, "_descartes", descartes_y_carrera)
    alertas.visibles("acme", AHORA)
    t = alertas.db.alerta_descartada
    with alertas.db.conectar() as con:
        assert [f.huella for f in con.execute(sa.select(t.c.huella))] == [alertas.huella("v2")]


# ---------- quién ve qué ----------

def test_las_alertas_solo_admin_no_las_ve_el_cliente_y_al_admin_se_le_cuentan(alertas, monkeypatch):
    monkeypatch.setattr(alertas, "FUENTES", [("f", _fuente(
        _al(alertas, "llave:wavespeed", "bloquea", "puesta_a_punto", solo_admin=True),
        _al(alertas, "faltante:logo", "atencion", "faltantes"),
        _al(alertas, "worker:parado", "bloquea", "fallos", solo_admin=True)))])
    cliente = alertas.visibles("acme", AHORA)                          # rol por defecto: cliente
    assert _claves(cliente["visibles"]) == ["faltante:logo"]
    assert cliente["resumen"] == {"n": 1, "bloquea": 0, "atencion": 1, "info": 0}
    assert _claves(alertas.visibles("acme", AHORA, rol="cliente")["visibles"]) == ["faltante:logo"]
    admin = alertas.visibles("acme", AHORA, rol="admin")
    assert _claves(admin["visibles"]) == ["llave:wavespeed", "faltante:logo", "worker:parado"]
    assert admin["resumen"] == {"n": 3, "bloquea": 2, "atencion": 1, "info": 0}


def test_un_descarte_de_solo_admin_no_se_le_muestra_al_cliente_ni_lo_poda_su_pasada(alertas, monkeypatch):
    a = _al(alertas, "llave:wavespeed", "bloquea", "puesta_a_punto", solo_admin=True)
    _con(alertas, monkeypatch, a)
    alertas.descartar("acme", a["clave"], a["huella"])
    assert alertas.visibles("acme", AHORA)["descartadas"] == []
    assert _claves(alertas.visibles("acme", AHORA, rol="admin")["descartadas"]) == ["llave:wavespeed"]
    alertas.visibles("acme", AHORA)                                    # la pasada del cliente no poda un descarte vigente
    assert _claves(alertas.visibles("acme", AHORA, rol="admin")["descartadas"]) == ["llave:wavespeed"]


def test_calculadas_evita_recalcular_y_se_filtra_al_leer(alertas, monkeypatch):
    a = _al(alertas, "faltante:logo", "atencion")
    b = _al(alertas, "llave:meta", "bloquea", "puesta_a_punto", solo_admin=True)
    monkeypatch.setattr(alertas, "FUENTES", [("f", _fuente(a, b))])
    cacheadas = alertas.calcular("acme", AHORA)

    def no_debe_correr(cliente, ahora):
        raise AssertionError("no debía recalcular")
    monkeypatch.setattr(alertas, "FUENTES", [("f", no_debe_correr)])
    v = alertas.visibles("acme", AHORA, rol="cliente", calculadas=cacheadas)
    assert _claves(v["visibles"]) == ["faltante:logo"]
    assert _claves(alertas.visibles("acme", AHORA, rol="admin", calculadas=cacheadas)["visibles"]) == \
        ["llave:meta", "faltante:logo"]
    # los descartes sí se leen en vivo aunque el cálculo venga de la caché
    alertas.descartar("acme", a["clave"], a["huella"])
    v = alertas.visibles("acme", AHORA, calculadas=cacheadas)
    assert v["visibles"] == [] and _claves(v["descartadas"]) == ["faltante:logo"]


def test_visibles_no_modifica_la_lista_calculada(alertas, monkeypatch):
    a = _al(alertas, "faltante:logo", "atencion")
    _con(alertas, monkeypatch, a)
    cacheadas = alertas.calcular("acme", AHORA)
    copia = [dict(x) for x in cacheadas]
    alertas.descartar("acme", a["clave"], a["huella"])
    alertas.visibles("acme", AHORA, calculadas=cacheadas)
    assert cacheadas == copia            # «descartada_en» va en una copia: la caché sigue limpia


def test_descartar_desde_varios_hilos_deja_una_sola_fila(alertas):
    errores = []

    def hilo(i):
        try:
            alertas.descartar("acme", "faltante:logo", alertas.huella(i))
        except Exception as e:  # noqa: BLE001
            errores.append(e)
    hilos = [threading.Thread(target=hilo, args=(i,)) for i in range(8)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert errores == []
    t = alertas.db.alerta_descartada
    with alertas.db.conectar() as con:
        assert con.execute(sa.select(sa.func.count()).select_from(t)).scalar() == 1
