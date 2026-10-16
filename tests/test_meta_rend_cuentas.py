"""Cuentas que un proyecto lee (spec §5): país adivinado por el nombre, una
cuenta en un solo proyecto, quitar borra sus copias."""
import threading

import pytest
import sqlalchemy as sa

from meta_rendimiento import cuentas

HF = [{"id": "act_709406360806038", "name": "HappyFlops Norway", "currency": "SEK"},
      {"id": "act_883891256188845", "name": "HappyFlops Netherlands (Active)", "currency": "SEK"},
      {"id": "act_708698354181244", "name": "HappyFlops World Wide", "currency": "SEK"},
      {"id": "act_228061763662782", "name": "HappyFlops MX", "currency": "SEK"},
      {"id": "act_1236343913931133", "name": "HappyFlops Poland (old DK)", "currency": "SEK"},
      {"id": "act_335308812712423", "name": "HappyFlops Finland 2025", "currency": "SEK"}]


def test_adivinar_pais_por_nombre():
    esperado = ["NO", "NL", None, "MX", "PL", "FI"]
    assert [cuentas.adivinar_pais(c["name"]) for c in HF] == esperado
    assert cuentas.adivinar_pais("HappyFlops Sweden") == "SE"
    assert cuentas.adivinar_pais("") is None


def test_adivinar_pais_no_confunde_palabras_pegadas_ni_cola():
    # Nombres sin país no pueden dar uno por unir palabras («WorldWide», «HappyFlops») ni por
    # «Active»/«old»; y un país pegado a la marca sigue sin adivinarse (solo palabras sueltas).
    for nombre in ("WorldWide", "HappyFlops", "HappyFlops Active", "HappyFlops (old)", "Flops World Wide Active old",
                   None, "   ", "2025"):
        assert cuentas.adivinar_pais(nombre) is None, nombre
    assert cuentas.adivinar_pais("HappyFlops Sweden (Active)") == "SE"
    assert cuentas.adivinar_pais("happyflops mx") is None    # el código ISO suelto pide mayúsculas


def test_el_codigo_iso_suelto_solo_vale_como_ultima_palabra():
    # R7: «AD» (Andorra) o «IT» en medio de un nombre son siglas de la marca, no un país.
    assert cuentas.adivinar_pais("HappyFlops MX") == "MX"
    assert cuentas.adivinar_pais("HappyFlops AD Account") is None
    assert cuentas.adivinar_pais("IT Team Norway") == "NO"       # el nombre de país gana
    assert cuentas.adivinar_pais("IT Team") is None
    assert cuentas.adivinar_pais("HappyFlops MX (Active)") is None  # «Active» es la última palabra


def test_normalizar_id():
    assert cuentas.normalizar_id("123") == "act_123" and cuentas.normalizar_id("act_123") == "act_123"


def test_elegir_reemplaza_y_rechaza_cuentas_de_otro_proyecto(base_temporal, monkeypatch):
    borradas = []
    monkeypatch.setattr(cuentas, "_borrar_copias", lambda con, c, a: borradas.append((c, a)))
    r = cuentas.elegir("happyflops", [dict(c, pais=cuentas.adivinar_pais(c["name"])) for c in HF[:3]], usuario="admin")
    assert sorted(r["agregadas"]) == sorted(c["id"] for c in HF[:3]) and not r["rechazadas"]
    assert {c["ad_account_id"]: c["pais"] for c in cuentas.listar("happyflops")}["act_709406360806038"] == "NO"
    r = cuentas.elegir("otro", [HF[0], HF[3]])
    assert r["rechazadas"] == ["act_709406360806038"] and r["agregadas"] == ["act_228061763662782"]
    assert cuentas.dueno("act_709406360806038") == "happyflops"
    r = cuentas.elegir("happyflops", [HF[0]])
    assert sorted(r["quitadas"]) == sorted(["act_883891256188845", "act_708698354181244"])
    assert ("happyflops", "act_883891256188845") in borradas
    assert cuentas.ids("happyflops") == ["act_709406360806038"]
    assert sorted(cuentas.todas()) == [("happyflops", "act_709406360806038"), ("otro", "act_228061763662782")]


def test_pais_invalido_se_guarda_vacio_y_cambiar_pais(base_temporal):
    cuentas.elegir("acme", [dict(HF[0], pais="ZZ")])
    assert cuentas.cuenta("acme", "act_709406360806038")["pais"] is None
    assert cuentas.cambiar_pais("acme", "act_709406360806038", "no")
    assert cuentas.cuenta("acme", "act_709406360806038")["pais"] == "NO"
    assert not cuentas.cambiar_pais("acme", "act_999", "NO")


def test_actualizar_extra_mezcla(base_temporal):
    cuentas.elegir("acme", [HF[0]])
    cuentas.actualizar_extra("acme", "act_709406360806038", {"a": 1})
    cuentas.actualizar_extra("acme", "act_709406360806038", {"b": 2})
    assert cuentas.cuenta("acme", "act_709406360806038")["extra"] == {"a": 1, "b": 2}
    cuentas.actualizar_extra("acme", "act_999", {"x": 1})        # una cuenta que no existe no se crea ni falla
    assert cuentas.cuenta("acme", "act_999") is None


def test_elegir_idempotente_conserva_lo_ya_copiado_y_acepta_ids_sin_prefijo(base_temporal, monkeypatch):
    borradas = []
    monkeypatch.setattr(cuentas, "_borrar_copias", lambda con, c, a: borradas.append((c, a)))
    cuentas.elegir("acme", [HF[0]])
    cuentas.actualizar("acme", "709406360806038", estado="ok", ultima_copia="2026-10-08 10:00:00",
                       moneda="NOK", inventado="no se guarda")
    # Elegir de nuevo la misma cuenta (sin «act_») no la toca, ni la agrega, ni borra copias.
    r = cuentas.elegir("acme", [{"id": "709406360806038", "name": "Otro nombre", "currency": "EUR"}])
    assert r == {"agregadas": [], "quitadas": [], "rechazadas": [], "fallos_r2": []} and not borradas
    c = cuentas.cuenta("acme", "act_709406360806038")
    assert (c["estado"], c["moneda"], c["nombre"]) == ("ok", "NOK", "HappyFlops Norway")
    assert c["ultima_copia"] == "2026-10-08 10:00:00" and "inventado" not in c
    # Una selección vacía (o con entradas sin id) quita todas las del proyecto.
    r = cuentas.elegir("acme", [{"name": "sin id"}])
    assert r["quitadas"] == ["act_709406360806038"] and cuentas.ids("acme") == []
    assert borradas == [("acme", "act_709406360806038")]


def test_la_carrera_por_la_misma_cuenta_la_rechaza_el_indice(base_temporal, monkeypatch):
    # Otro proyecto la tomó entre el chequeo y el insert: el índice único responde y va a rechazadas.
    monkeypatch.setattr(cuentas, "_borrar_copias", lambda con, c, a: None)
    cuentas.elegir("happyflops", [HF[0]])
    monkeypatch.setattr(cuentas, "_dueno", lambda con, act: None)
    r = cuentas.elegir("otro", [HF[0]])
    assert r == {"agregadas": [], "quitadas": [], "rechazadas": ["act_709406360806038"], "fallos_r2": []}
    assert cuentas.ids("otro") == []


def test_listar_ordena_por_nombre_y_aisla_proyectos(base_temporal, monkeypatch):
    monkeypatch.setattr(cuentas, "_borrar_copias", lambda con, c, a: None)
    cuentas.elegir("acme", [HF[3], HF[0], HF[1]])
    cuentas.elegir("otro", [HF[2]])
    assert [c["nombre"] for c in cuentas.listar("acme")] == [
        "HappyFlops MX", "HappyFlops Netherlands (Active)", "HappyFlops Norway"]
    assert cuentas.ids("otro") == ["act_708698354181244"]
    assert cuentas.listar("nadie") == [] and cuentas.cuenta("acme", "act_708698354181244") is None
    # Una cuenta de otro proyecto no se puede editar desde éste.
    assert not cuentas.cambiar_pais("acme", "act_708698354181244", "SE")
    cuentas.actualizar("acme", "act_708698354181244", estado="error")
    cuentas.actualizar_extra("acme", "act_708698354181244", {"x": 1})
    otra = cuentas.cuenta("otro", "act_708698354181244")
    assert otra["estado"] == "nueva" and otra["extra"] == {}


def test_si_borrar_copias_falla_la_cuenta_sigue_y_el_siguiente_elegir_reintenta(base_temporal, monkeypatch):
    # R5: primero las copias, después la fila; si las copias fallan la fila sobrevive y no quedan huérfanas.
    llamadas = []

    def _borrar(con, c, a):
        llamadas.append((c, a))
        if len(llamadas) == 1:
            raise RuntimeError("falló el borrado de copias")
    monkeypatch.setattr(cuentas, "_borrar_copias", _borrar)
    cuentas.elegir("acme", [HF[0], HF[1]])
    with pytest.raises(RuntimeError):
        cuentas.elegir("acme", [HF[0]])
    assert llamadas == [("acme", "act_883891256188845")]
    assert cuentas.ids("acme") == ["act_883891256188845", "act_709406360806038"]    # nombre: Netherlands, Norway
    r = cuentas.elegir("acme", [HF[0]])
    assert r["quitadas"] == ["act_883891256188845"] and cuentas.ids("acme") == ["act_709406360806038"]
    assert llamadas == [("acme", "act_883891256188845")] * 2


def _sembrar_copias(cliente, act):
    """Una fila de cada copia de la cuenta (días, anuncio, objeto, alcance, desglose) y un análisis de fuente Meta."""
    from meta_rendimiento import datos
    from triple_whale import datos as tw_datos
    datos.reemplazar_cuenta_dias(cliente, act, "2026-10-01", "2026-10-01", [{"fecha": "2026-10-01", "gasto": 1}])
    datos.reemplazar_anuncio_dias(cliente, act, "2026-10-01", "2026-10-01",
                                  [{"fecha": "2026-10-01", "ad_id": "a1", "gasto": 1}])
    datos.guardar_objetos(cliente, act, [{"nivel": "anuncio", "objeto_id": f"{act}_a1", "nombre": "Video"}])
    datos.guardar_alcance(cliente, act, [{"nivel": "cuenta", "objeto_id": act, "ventana": 7, "alcance": 1}])
    datos.reemplazar_desgloses(cliente, act, 7, "pais", [{"clave": "NO", "gasto": 1}])
    return tw_datos.crear_analisis(cliente, None, "facebook-ads", "111", "2026-09-01", "2026-09-30", "SEK",
                                   {"fuente": "meta", "ad_account_id": act, "nombre": "Video"})


def _filas_de(cliente, act):
    import db
    with db.conectar() as con:
        n = sum(con.execute(sa.select(sa.func.count()).select_from(t).where(
            t.c.cliente == cliente, t.c.ad_account_id == act)).scalar()
            for t in (db.meta_cuenta_dia, db.meta_anuncio_dia, db.meta_objeto, db.meta_alcance, db.meta_desglose))
        return n + con.execute(sa.select(sa.func.count()).select_from(db.tw_analisis).where(
            db.tw_analisis.c.cliente == cliente)).scalar()


def test_pnd206_elegir_es_una_sola_transaccion(base_temporal, monkeypatch):
    """PND-206 (decisión 2026-10-13): agregar y quitar pasan enteros o no pasan. Si borrar las copias de la quitada
    falla, la agregada tampoco entra, la quitada sigue con todas sus copias y no se borra nada de R2."""
    from meta_rendimiento import creativo, datos
    norway, sweden = HF[0], dict(HF[1], id="act_2")
    cuentas.elegir("acme", [norway, sweden])
    _sembrar_copias("acme", "act_2")
    antes = _filas_de("acme", "act_2")
    r2 = []
    monkeypatch.setattr(creativo, "borrar_copias", lambda c, filas: r2.append(filas) or (0, []))
    real = datos.borrar_cuenta

    def a_medias(cliente, act, con=None):
        real(cliente, act, con=con)           # alcanza a borrar las métricas…
        raise RuntimeError("disco lleno")     # …y falla antes de los análisis y de la fila de la cuenta
    monkeypatch.setattr(datos, "borrar_cuenta", a_medias)
    with pytest.raises(RuntimeError):
        cuentas.elegir("acme", [norway, HF[2]])
    assert sorted(cuentas.ids("acme")) == sorted([norway["id"], "act_2"])     # HF[2] no entró: nada cambió
    assert _filas_de("acme", "act_2") == antes and r2 == []
    monkeypatch.setattr(datos, "borrar_cuenta", real)
    r = cuentas.elegir("acme", [norway, HF[2]])
    assert r["quitadas"] == ["act_2"] and r["agregadas"] == [HF[2]["id"]]
    assert _filas_de("acme", "act_2") == 0 and len(r2) == 1


def test_pnd206_una_copia_que_escribe_mientras_se_suelta_la_cuenta_no_deja_huerfanas(base_temporal):
    """La copia comprueba la cuenta en la MISMA transacción en la que escribe: si `elegir` la está quitando, espera a
    que termine, ve que ya no está y no escribe (CuentaSoltada). Sin esa comprobación la copia volvía a escribir días
    de una cuenta que ya no estaba en `meta_cuenta` y nadie los borraba."""
    import db
    from meta_rendimiento import datos
    act = HF[0]["id"]
    cuentas.elegir("acme", [HF[0]])
    pausado, soltar = threading.Event(), threading.Event()
    a = {"ident": None, "hecho": False}
    errores, resultado = [], []

    @sa.event.listens_for(db.engine(), "after_cursor_execute")
    def _pausar(conn, cursor, statement, parameters, context, executemany):
        if threading.get_ident() == a["ident"] and not a["hecho"] and statement.lstrip().upper().startswith("DELETE"):
            a["hecho"] = True               # `elegir` ya tomó el candado y empezó a borrar copias
            pausado.set()
            soltar.wait(timeout=10)

    def _elegir():
        a["ident"] = threading.get_ident()
        try:
            cuentas.elegir("acme", [])
        except Exception as e:  # noqa: BLE001
            errores.append(e)

    def _copia():
        try:
            datos.reemplazar_cuenta_dias("acme", act, "2026-10-01", "2026-10-01",
                                         [{"fecha": "2026-10-01", "gasto": 9}], exigir_cuenta=True)
            resultado.append("escribió")
        except datos.CuentaSoltada:
            resultado.append("soltada")
        except Exception as e:  # noqa: BLE001
            errores.append(e)

    ta = threading.Thread(target=_elegir)
    ta.start()
    assert pausado.wait(timeout=10)
    tb = threading.Thread(target=_copia)
    tb.start()
    tb.join(0.3)
    assert tb.is_alive()                     # la copia espera el candado de `elegir`
    soltar.set()
    ta.join(10)
    tb.join(10)
    sa.event.remove(db.engine(), "after_cursor_execute", _pausar)
    assert errores == [] and resultado == ["soltada"]
    assert cuentas.ids("acme") == [] and _filas_de("acme", act) == 0


def test_pnd206_con_la_cuenta_elegida_la_copia_escribe(base_temporal):
    from meta_rendimiento import datos
    cuentas.elegir("acme", [HF[0]])
    assert datos.reemplazar_cuenta_dias("acme", HF[0]["id"], "2026-10-01", "2026-10-01",
                                        [{"fecha": "2026-10-01", "gasto": 9}], exigir_cuenta=True) == 1
    with pytest.raises(datos.CuentaSoltada):
        datos.guardar_objetos("otro", HF[0]["id"], [{"nivel": "anuncio", "objeto_id": "a1"}], exigir_cuenta=True)
    with pytest.raises(datos.CuentaSoltada):
        datos.guardar_alcance("acme", "act_9", [{"nivel": "cuenta", "objeto_id": "act_9", "ventana": 7}],
                              exigir_cuenta=True)
    with pytest.raises(datos.CuentaSoltada):
        datos.reemplazar_desgloses("acme", "act_9", 7, "pais", [{"clave": "NO"}], exigir_cuenta=True)
    assert _filas_de("otro", HF[0]["id"]) == 0 and _filas_de("acme", "act_9") == 0


def test_actualizar_extra_no_pierde_la_escritura_de_otro_hilo(base_temporal):
    # R6: el lock de escritura se toma ANTES de leer `extra`. El hilo A se detiene tras su primera sentencia
    # sobre meta_cuenta; B intenta escribir mientras tanto. Sin el lock previo B escribe en medio y A la pisa.
    import db
    cuentas.elegir("acme", [HF[0]])
    act = "act_709406360806038"
    pausado, soltar, b_intenta = threading.Event(), threading.Event(), threading.Event()
    a = {"ident": None, "hecho": False}
    errores = []

    @sa.event.listens_for(db.engine(), "after_cursor_execute")
    def _pausar(conn, cursor, statement, parameters, context, executemany):
        if (threading.get_ident() == a["ident"] and not a["hecho"] and "meta_cuenta" in statement):
            a["hecho"] = True
            pausado.set()
            soltar.wait(timeout=10)

    def _escribir(clave, valor, antes=None):
        try:
            if antes:
                antes()
            cuentas.actualizar_extra("acme", act, {clave: valor})
        except Exception as e:  # noqa: BLE001
            errores.append(e)

    def _hilo_a():
        a["ident"] = threading.get_ident()
        _escribir("a", 1)

    ta = threading.Thread(target=_hilo_a)
    ta.start()
    assert pausado.wait(timeout=10)
    tb = threading.Thread(target=_escribir, args=("b", 2, b_intenta.set))
    tb.start()
    assert b_intenta.wait(timeout=10)
    tb.join(0.3)        # sin el lock previo B termina aquí; con él espera a que A suelte
    soltar.set()
    ta.join(10)
    tb.join(10)
    assert not ta.is_alive() and not tb.is_alive() and errores == []
    assert cuentas.cuenta("acme", act)["extra"] == {"a": 1, "b": 2}
