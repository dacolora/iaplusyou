"""Copia de Triple Whale a la base (spec 2026-09-28 §4) y sus tareas del worker."""
from datetime import date, datetime

import pytest

import triple_whale
import triple_whale_tiendas
from triple_whale import datos, sync

HOY = date(2026, 9, 28)


@pytest.fixture()
def conectado(base_temporal, monkeypatch):
    monkeypatch.setenv("FLASK_SECRET_KEY", "test_secret_key_12345678")
    triple_whale_tiendas.conectar("acme", "tw_secreto", "acme.myshopify.com", moneda="USD",
                                  modelo_atribucion="Last Click", ventana_atribucion="7_days")
    return base_temporal


def _tienda(cliente="acme"):
    """El id de la (única) tienda conectada en la prueba."""
    return triple_whale_tiendas.tiendas(cliente)[0]["id"]


class TripleWhaleFalso:
    """Responde según la tabla que nombra la consulta. `fallar` = {tabla: n}
    hace que las primeras n consultas completas de esa tabla den
    ErrorConsulta (columna que la cuenta no tiene)."""
    def __init__(self, ads=(), pixel=(), tienda=(), fallar=None, error=None, fallar_todo=(), productos=()):
        self.ads, self.pixel, self.tienda, self.productos = list(ads), list(pixel), list(tienda), list(productos)
        self.fallar = dict(fallar or {})
        self.fallar_todo = set(fallar_todo)
        self.error = error
        self.llamadas = []

    def __call__(self, llave, shop, consulta, desde, hasta, moneda=None):
        tabla = ("pixel" if "pixel_joined_tvf" in consulta else "tienda" if "blended_stats_tvf" in consulta
                 else "productos" if "orders_table" in consulta else "ads")
        completa = ("outbound_clicks" in consulta or "sessions" in consulta or "net_profit" in consulta
                    or "products_info.title" in consulta)
        self.llamadas.append((tabla, "completa" if completa else "minima", desde, hasta, moneda, llave, shop))
        if self.error:
            raise self.error
        if completa and self.fallar.get(tabla):
            self.fallar[tabla] -= 1
            raise triple_whale.ErrorConsulta("Unknown identifier")
        if tabla in self.fallar_todo:
            raise triple_whale.ErrorConsulta(f"{tabla}: no existe")
        filas = {"ads": self.ads, "pixel": self.pixel, "tienda": self.tienda, "productos": self.productos}[tabla]
        return [f for f in filas if desde <= str(f.get("event_date"))[:10] <= hasta]


def _ad(ad_id, fecha, **kw):
    fila = {"channel": "facebook-ads", "ad_id": ad_id, "event_date": fecha, "campaign_name": "Camp", "ad_name": f"Ad {ad_id}",
            "spend": "10", "impressions": "1000", "clicks": "20", "thruplays": "100", "video_3s": "300",
            "is_utm_valid": 1}
    fila.update(kw)
    return fila


# ---------------------------------------------------------- normalizar ---

def test_normalizar_anuncio_convierte_tipos_y_descarta_filas_sin_anuncio():
    r = sync.normalizar_anuncio(_ad("123", "2026-09-01T00:00:00", spend="12.345", is_utm_valid="false",
                                    outbound_clicks="7"))
    assert r["ad_id"] == "123" and r["fecha"] == "2026-09-01" and r["canal"] == "facebook-ads"
    assert r["gasto"] == 12.345 and r["impresiones"] == 1000 and r["clics_salida"] == 7 and r["vistas_3s"] == 300
    assert r["utm_ok"] is False and r["anuncio"] == "Ad 123"
    assert sync.normalizar_anuncio({"channel": "google-ads", "ad_id": "", "event_date": "2026-09-01"}) is None
    assert sync.normalizar_anuncio({"channel": "x", "ad_id": "1", "event_date": "ayer"}) is None
    # La consulta mínima no trae dimensiones: no se inventan (None ≠ vacío).
    assert "cuenta_id" not in sync.normalizar_anuncio({"ad_id": "1", "event_date": "2026-09-01"})


def test_normalizar_pixel_y_tienda():
    p = sync.normalizar_pixel({"channel": "facebook-ads", "ad_id": 5, "event_date": "2026-09-02", "orders": "1.5",
                               "revenue": "90", "nc_orders": 1})
    assert p["ad_id"] == "5" and p["pedidos"] == 1.5 and p["ingresos"] == 90.0 and p["sesiones"] == 0
    t = sync.normalizar_tienda({"event_date": "2026-09-02", "spend": 10, "revenue": "250.5", "orders": 3})
    assert t["fecha"] == "2026-09-02" and t["ingresos"] == 250.5 and t["reembolsos"] == 0.0
    assert sync.normalizar_tienda({"event_date": None}) is None


def test_tramos():
    assert sync.tramos("2026-09-01", "2026-09-16", 7) == [("2026-09-01", "2026-09-07"), ("2026-09-08", "2026-09-14"),
                                                          ("2026-09-15", "2026-09-16")]
    assert sync.tramos("2026-09-01", "2026-09-01") == [("2026-09-01", "2026-09-01")]


def test_rango_pendiente():
    # Nunca se copió: los 90 días.
    assert sync.rango_pendiente({"extra": {}}, HOY) == ("2026-07-01", "2026-09-28")
    # Al día: los últimos 7.
    reciente = {"extra": {"backfill_desde": "2026-07-01"}, "ultima_sincronizacion": "2026-09-28T08:00:00"}
    assert sync.rango_pendiente(reciente, HOY) == ("2026-09-22", "2026-09-28")
    # El worker estuvo parado 12 días: desde dos días antes de la última copia.
    parado = {"extra": {"backfill_desde": "2026-06-01"}, "ultima_sincronizacion": "2026-09-16T08:00:00"}
    assert sync.rango_pendiente(parado, HOY) == ("2026-09-14", "2026-09-28")


def test_esta_fresca():
    ahora = datetime(2026, 9, 28, 10, 0, 0)
    base = {"extra": {"backfill_desde": "2026-07-01"}}
    assert sync.esta_fresca(dict(base, ultima_sincronizacion="2026-09-28T09:45:00"), 30, ahora)
    assert not sync.esta_fresca(dict(base, ultima_sincronizacion="2026-09-28T09:00:00"), 30, ahora)
    assert not sync.esta_fresca({"extra": {}, "ultima_sincronizacion": "2026-09-28T09:59:00"}, 30, ahora)


# --------------------------------------------------------- sincronizar ---

def test_sincronizar_copia_anuncios_pixel_y_tienda(conectado, monkeypatch):
    falso = TripleWhaleFalso(
        ads=[_ad("1", "2026-09-27"), _ad("1", "2026-09-28", spend="5"), _ad("2", "2026-09-28")],
        pixel=[{"channel": "facebook-ads", "ad_id": "1", "event_date": "2026-09-28", "orders": 2, "revenue": 80}],
        tienda=[{"event_date": "2026-09-28", "spend": 25, "revenue": 300, "orders": 4}])
    monkeypatch.setattr(triple_whale, "sql_query", falso)
    progreso = []
    r = sync.sincronizar("acme", _tienda(), "2026-09-22", "2026-09-28", on_progreso=lambda *a: progreso.append(a), hoy=HOY)
    assert r["anuncios"] == 2 and r["dias_tienda"] == 1 and r["filas_pixel"] == 1 and r["fallos"] == {}
    assert r["consultas"] == {"anuncios": "completa", "pixel": "completa", "tienda": "completa", "productos": "completa"}
    assert progreso == [(0, 1, "2026-09-22", "2026-09-28")]
    # La llave, la tienda y la moneda de la conexión van en cada consulta.
    assert {(l[4], l[5], l[6]) for l in falso.llamadas} == {("USD", "tw_secreto", "acme.myshopify.com")}
    tot = datos.totales_anuncio("acme", _tienda(), "facebook-ads", "1", "2026-09-01")
    assert tot["gasto"] == 15.0 and tot["pedidos"] == 2.0 and tot["ingresos"] == 80.0 and tot["con_pixel"]
    assert datos.serie_tienda("acme", None, "2026-09-28", "2026-09-28")[0]["ingresos"] == 300.0
    c = triple_whale_tiendas.tienda("acme", _tienda())
    assert c["estado"] == "conectada" and c["ultima_sincronizacion"] and c["extra"]["backfill_desde"] == "2026-09-22"
    assert c["extra"]["ultimo_resumen"]["anuncios"] == 2


def test_sincronizar_de_nuevo_reemplaza_lo_reatribuido(conectado, monkeypatch):
    """Triple Whale movió el pedido del anuncio 1 al 2: la segunda copia no
    puede dejar el del 1 viejo (cero en el rango antes de escribir)."""
    ads = [_ad("1", "2026-09-28"), _ad("2", "2026-09-28")]
    monkeypatch.setattr(triple_whale, "sql_query", TripleWhaleFalso(ads=ads, pixel=[
        {"channel": "facebook-ads", "ad_id": "1", "event_date": "2026-09-28", "orders": 1, "revenue": 50}]))
    sync.sincronizar("acme", _tienda(), "2026-09-28", "2026-09-28", hoy=HOY)
    monkeypatch.setattr(triple_whale, "sql_query", TripleWhaleFalso(ads=ads, pixel=[
        {"channel": "facebook-ads", "ad_id": "2", "event_date": "2026-09-28", "orders": 1, "revenue": 50}]))
    sync.sincronizar("acme", _tienda(), "2026-09-28", "2026-09-28", hoy=HOY)
    uno = datos.totales_anuncio("acme", _tienda(), "facebook-ads", "1", "2026-09-28")
    dos = datos.totales_anuncio("acme", _tienda(), "facebook-ads", "2", "2026-09-28")
    # El Pixel respondió para ese día: el 1 queda en 0 pedidos (dato, no ausencia de dato).
    assert uno["pedidos"] == 0 and uno["con_pixel"] and dos["pedidos"] == 1 and dos["con_pixel"]
    assert datos.rango("acme")["filas"] == 2


def test_sincronizar_baja_a_la_consulta_minima_y_no_vuelve_a_probar_la_completa(conectado, monkeypatch):
    falso = TripleWhaleFalso(ads=[_ad("1", "2026-09-10")], fallar={"ads": 1})
    monkeypatch.setattr(triple_whale, "sql_query", falso)
    r = sync.sincronizar("acme", _tienda(), "2026-09-01", "2026-09-14", hoy=HOY)
    ads = [l for l in falso.llamadas if l[0] == "ads"]
    assert [l[1] for l in ads] == ["completa", "minima", "minima"]   # 2 tramos: el segundo va directo a la mínima
    assert r["consultas"]["anuncios"] == "minima" and r["anuncios"] == 1


def test_sin_pixel_ni_tienda_los_anuncios_igual_llegan(conectado, monkeypatch):
    falso = TripleWhaleFalso(ads=[_ad("1", "2026-09-28")], fallar_todo={"pixel", "tienda"})
    monkeypatch.setattr(triple_whale, "sql_query", falso)
    r = sync.sincronizar("acme", _tienda(), "2026-09-15", "2026-09-28", hoy=HOY)
    assert r["anuncios"] == 1 and set(r["fallos"]) == {"pixel", "tienda"}
    assert r["consultas"]["pixel"] == "sin_datos"
    # Tras el primer fallo del Pixel no se insiste en cada tramo.
    assert len([l for l in falso.llamadas if l[0] == "pixel"]) == 2
    assert datos.totales_anuncio("acme", _tienda(), "facebook-ads", "1", "2026-09-01")["gasto"] == 10.0


def test_normalizar_producto():
    r = sync.normalizar_producto({"event_date": "2026-09-28", "product_id": 8891, "title": "Cojín", "sku": "C-1",
                                  "quantity": "3", "revenue": "89.7", "orders": 2})
    assert r == {"fecha": "2026-09-28", "producto_id": "8891", "nombre": "Cojín", "sku": "C-1", "unidades": 3.0,
                 "ingresos": 89.7, "pedidos": 2.0}
    assert sync.normalizar_producto({"event_date": "2026-09-28", "product_id": None}) is None
    assert sync.normalizar_producto({"event_date": "x", "product_id": "1"}) is None


def test_sincronizar_copia_ventas_por_producto_y_suma_variantes(conectado, monkeypatch):
    """Dos filas del mismo producto y día (dos variantes) se suman; el top
    del periodo sale por ingresos."""
    falso = TripleWhaleFalso(ads=[_ad("1", "2026-09-28")], productos=[
        {"event_date": "2026-09-28", "product_id": "p1", "title": "Cojín", "sku": "C-1", "quantity": 2, "revenue": 60, "orders": 2},
        {"event_date": "2026-09-28", "product_id": "p1", "title": None, "sku": "C-1b", "quantity": 1, "revenue": 30, "orders": 1},
        {"event_date": "2026-09-28", "product_id": "p2", "title": "Lámpara", "sku": "L-1", "quantity": 1, "revenue": 200, "orders": 1},
        {"event_date": "2026-09-27", "product_id": "p1", "title": "Cojín", "sku": "C-1", "quantity": 5, "revenue": 150, "orders": 4}])
    monkeypatch.setattr(triple_whale, "sql_query", falso)
    r = sync.sincronizar("acme", _tienda(), "2026-09-27", "2026-09-28", hoy=HOY)
    assert r["productos"] == 2 and r["consultas"]["productos"] == "completa"
    top = datos.top_productos("acme", None, "2026-09-27", "2026-09-28")
    assert [(p["producto_id"], p["nombre"], p["ingresos"], p["unidades"], p["pedidos"]) for p in top] == [
        ("p1", "Cojín", 240.0, 8.0, 7.0), ("p2", "Lámpara", 200.0, 1.0, 1.0)]
    assert datos.hay_productos("acme")
    # Una segunda copia del mismo rango reemplaza, no duplica.
    sync.sincronizar("acme", _tienda(), "2026-09-27", "2026-09-28", hoy=HOY)
    assert datos.top_productos("acme", None, "2026-09-27", "2026-09-28")[0]["ingresos"] == 240.0


def test_sin_products_info_la_copia_sigue_sin_productos(conectado, monkeypatch):
    falso = TripleWhaleFalso(ads=[_ad("1", "2026-09-28")], fallar_todo={"productos"})
    monkeypatch.setattr(triple_whale, "sql_query", falso)
    r = sync.sincronizar("acme", _tienda(), "2026-09-22", "2026-09-28", hoy=HOY)
    assert r["anuncios"] == 1 and "productos" in r["fallos"] and r["consultas"]["productos"] == "sin_datos"
    assert not datos.hay_productos("acme")


def test_sincronizar_con_llave_revocada_sube_el_error(conectado, monkeypatch):
    monkeypatch.setattr(triple_whale, "sql_query", TripleWhaleFalso(error=triple_whale.ErrorLlave("revocada")))
    with pytest.raises(triple_whale.ErrorLlave):
        sync.sincronizar("acme", _tienda(), hoy=HOY)
    assert triple_whale_tiendas.tienda("acme", _tienda())["ultima_sincronizacion"] is None


def test_sincronizar_si_hace_falta(conectado, monkeypatch):
    llamadas = []
    monkeypatch.setattr(sync, "sincronizar", lambda cliente, tienda_id: llamadas.append((cliente, tienda_id)) or {"ok": 1})
    tid = _tienda()
    assert sync.sincronizar_si_hace_falta("acme", tid) == {"ok": 1}   # nunca se copió
    triple_whale_tiendas.actualizar_tienda("acme", tid, ultima_sincronizacion=datetime.now().isoformat(timespec="seconds"))
    triple_whale_tiendas.actualizar_extra_tienda("acme", tid, {"backfill_desde": "2026-07-01"})
    assert sync.sincronizar_si_hace_falta("acme", tid) is None
    assert sync.sincronizar_si_hace_falta("nadie", tid) is None
    assert sync.sincronizar_si_hace_falta("acme", 9999) is None
    assert llamadas == [("acme", tid)]


# ------------------------------------------------------------- tareas ---

def _payload(tid, cliente="acme"):
    return {"cliente": cliente, "tienda_id": tid}


def test_tarea_sincronizar_ok_y_error_sin_token(conectado, monkeypatch):
    from tareas import triple_whale as t
    tid = _tienda()
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(t.avisos, "revisar_y_avisar", lambda cliente: None)
    monkeypatch.setattr(triple_whale, "sql_query", TripleWhaleFalso(ads=[_ad("1", "2026-09-28")]))
    monkeypatch.setattr(sync, "rango_pendiente", lambda tienda, hoy: ("2026-09-28", "2026-09-28"))
    texto = t.tw_sincronizar({"payload": _payload(tid), "job_id": t.job_id_sync("acme", tid)})
    assert "1 anuncio" in texto

    monkeypatch.setattr(triple_whale, "sql_query", TripleWhaleFalso(
        error=triple_whale.ErrorLlave("revocada x-api-key: tw_secreto")))
    with pytest.raises(triple_whale.ErrorTripleWhale) as e:
        t.tw_sincronizar({"payload": _payload(tid)})
    c = triple_whale_tiendas.tienda("acme", tid)
    assert c["estado"] == "error" and "tw_secreto" not in c["error"] and "tw_secreto" not in str(e.value)
    assert "revocada" in c["error"]


def test_tarea_sincronizar_avisa_lo_que_cambio_y_no_se_cae_si_el_aviso_falla(conectado, monkeypatch):
    from tareas import triple_whale as t
    tid = _tienda()
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(triple_whale, "sql_query", TripleWhaleFalso(ads=[_ad("1", "2026-09-28")]))
    monkeypatch.setattr(sync, "rango_pendiente", lambda tienda, hoy: ("2026-09-28", "2026-09-28"))
    monkeypatch.setattr(t.avisos, "revisar_y_avisar", lambda cliente: {
        "ganadores": [1, 2], "cansados": [], "perdedores": [3], "avisado": True})
    texto = t.tw_sincronizar({"payload": _payload(tid)})
    assert "Aviso enviado: 2 ganador(es)" in texto and "1 perdedor(es)" in texto

    def _revienta(cliente):
        raise RuntimeError("smtp caído")
    monkeypatch.setattr(t.avisos, "revisar_y_avisar", _revienta)
    assert "Listo" in t.tw_sincronizar({"payload": _payload(tid)})


def test_tarea_sincronizar_sin_conexion_no_falla(conectado):
    from tareas import triple_whale as t
    assert "ya no está conectada" in t.tw_sincronizar({"payload": _payload(9999)})
    assert "ya no está conectada" in t.tw_sincronizar({"payload": _payload(_tienda(), "nadie")})


# ---------------------------------------------------- varias tiendas ---

@pytest.fixture()
def dos_tiendas(conectado, monkeypatch):
    """acme tiene Colombia (la del fixture, llave tw_secreto) y Noruega (llave tw_noruega)."""
    from tareas import triple_whale as t
    triple_whale_tiendas.cambiar_pais("acme", _tienda(), "CO")
    no = triple_whale_tiendas.agregar("acme", "tw_noruega", "no-acme.myshopify.com", "NO")
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(t.avisos, "revisar_y_avisar", lambda cliente: None)
    monkeypatch.setattr(sync, "rango_pendiente", lambda tienda, hoy: ("2026-09-28", "2026-09-28"))
    return _tienda(), no


def test_cada_tienda_copia_con_su_llave_y_su_dominio(dos_tiendas, monkeypatch):
    co, no = dos_tiendas
    falso = TripleWhaleFalso(ads=[_ad("1", "2026-09-28")])
    monkeypatch.setattr(triple_whale, "sql_query", falso)
    sync.sincronizar("acme", co, hoy=HOY)
    assert {(l[5], l[6]) for l in falso.llamadas} == {("tw_secreto", "acme.myshopify.com")}
    falso.llamadas.clear()
    sync.sincronizar("acme", no, hoy=HOY)
    assert {(l[5], l[6]) for l in falso.llamadas} == {("tw_noruega", "no-acme.myshopify.com")}
    # Cada copia quedó en su tienda y solo en la suya.
    assert datos.totales_anuncio("acme", co, "facebook-ads", "1", "2026-09-28")["gasto"] == 10.0
    assert datos.totales_anuncio("acme", no, "facebook-ads", "1", "2026-09-28")["gasto"] == 10.0
    assert triple_whale_tiendas.tienda("acme", co)["extra"]["backfill_desde"]
    assert triple_whale_tiendas.tienda("acme", no)["ultima_sincronizacion"]


def test_error_en_una_tienda_no_toca_a_la_otra_ni_guarda_su_llave(dos_tiendas, monkeypatch):
    from tareas import triple_whale as t
    co, no = dos_tiendas

    def responde(llave, shop, consulta, desde, hasta, moneda=None):
        if shop == "no-acme.myshopify.com":
            raise triple_whale.ErrorLlave("revocada tw_noruega x-api-key: tw_noruega")
        return []
    monkeypatch.setattr(triple_whale, "sql_query", responde)
    t.tw_sincronizar({"payload": _payload(co)})
    with pytest.raises(triple_whale.ErrorTripleWhale) as e:
        t.tw_sincronizar({"payload": _payload(no)})
    malo, bueno = triple_whale_tiendas.tienda("acme", no), triple_whale_tiendas.tienda("acme", co)
    assert malo["estado"] == "error" and "tw_noruega" not in malo["error"] and "tw_noruega" not in str(e.value)
    assert "revocada" in malo["error"]
    assert bueno["estado"] == "conectada" and not bueno["error"]


def test_tarea_dice_el_pais_de_la_tienda(dos_tiendas, monkeypatch):
    from tareas import triple_whale as t
    co, no = dos_tiendas
    monkeypatch.setattr(triple_whale, "sql_query", TripleWhaleFalso(ads=[_ad("1", "2026-09-28")]))
    assert "Noruega" in t.tw_sincronizar({"payload": _payload(no)})


def _jobs_tw():
    import sqlalchemy as sa
    import db
    with db.conectar() as con:
        return sorted(r[0] for r in con.execute(sa.select(db.tarea.c.job_id).where(db.tarea.c.tipo == "tw_sincronizar")))


def test_periodica_encola_una_por_tienda_conectada(dos_tiendas):
    from tareas import triple_whale as t
    triple_whale_tiendas.conectar("otro", "tw_y", "otro.myshopify.com")
    co, no = dos_tiendas
    assert "3" in t.tw_sincronizar_todas({"payload": {}})
    assert "0" in t.tw_sincronizar_todas({"payload": {}})   # ya había una viva por tienda
    otro = triple_whale_tiendas.tiendas("otro")[0]["id"]
    assert _jobs_tw() == sorted([f"acme__tw_sync__{co}", f"acme__tw_sync__{no}", f"otro__tw_sync__{otro}"])


def test_encolar_sync_encola_las_del_proyecto_o_una_sola(dos_tiendas):
    from tareas import triple_whale as t
    co, no = dos_tiendas
    assert t.job_id_sync("acme", co) == f"acme__tw_sync__{co}"
    assert t.encolar_sync("acme") == 2
    assert t.encolar_sync("acme") == 0
    assert t.syncs_en_curso("acme") == sorted([t.job_id_sync("acme", co), t.job_id_sync("acme", no)])
    assert t.syncs_en_curso("otro") == []
    assert t.encolar_sync("acme", co) == 0     # esa ya estaba viva
    assert t.encolar_sync("acme", 9999) == 0   # no existe (o es de otro proyecto)


def test_encolar_sync_de_una_tienda_lleva_su_payload_y_dos_intentos(dos_tiendas):
    import sqlalchemy as sa
    import db
    from tareas import triple_whale as t
    co, no = dos_tiendas
    assert t.encolar_sync("acme", no) == 1
    with db.conectar() as con:
        fila = con.execute(sa.select(db.tarea.c.payload, db.tarea.c.max_intentos).where(
            db.tarea.c.job_id == t.job_id_sync("acme", no))).first()
    assert fila.payload == {"cliente": "acme", "tienda_id": no} and fila.max_intentos == 2


def test_los_avisos_corren_solo_cuando_termina_la_ultima_copia(dos_tiendas, monkeypatch):
    from tareas import triple_whale as t
    co, no = dos_tiendas
    llamadas = []
    monkeypatch.setattr(t.avisos, "revisar_y_avisar", lambda cliente: llamadas.append(cliente))
    monkeypatch.setattr(triple_whale, "sql_query", TripleWhaleFalso(ads=[_ad("1", "2026-09-28")]))
    t.encolar_sync("acme")
    # La de Colombia termina mientras la de Noruega sigue en cola: no avisa.
    t.tw_sincronizar({"payload": _payload(co), "job_id": t.job_id_sync("acme", co)})
    assert llamadas == []
    # Cuando la de Colombia ya no está viva, la de Noruega es la última y sí avisa, una vez.
    import cola
    cola.terminar(cola.consultar_por_job(t.job_id_sync("acme", co))["id"])
    t.tw_sincronizar({"payload": _payload(no), "job_id": t.job_id_sync("acme", no)})
    assert llamadas == ["acme"]


def test_una_sola_tienda_avisa_siempre(conectado, monkeypatch):
    from tareas import triple_whale as t
    llamadas = []
    monkeypatch.setattr(t.trabajos, "reportar", lambda *a, **k: None)
    monkeypatch.setattr(t.avisos, "revisar_y_avisar", lambda cliente: llamadas.append(cliente))
    monkeypatch.setattr(triple_whale, "sql_query", TripleWhaleFalso(ads=[_ad("1", "2026-09-28")]))
    monkeypatch.setattr(sync, "rango_pendiente", lambda tienda, hoy: ("2026-09-28", "2026-09-28"))
    tid = _tienda()
    t.encolar_sync("acme", tid)   # la propia tarea está viva mientras corre: no cuenta como «otra»
    t.tw_sincronizar({"payload": _payload(tid), "job_id": t.job_id_sync("acme", tid)})
    assert llamadas == ["acme"]


def test_tareas_registradas_y_periodica_antes_de_refrescar_experimentos():
    import tareas
    import worker
    tareas.cargar_todas()
    assert {"tw_sincronizar", "tw_sincronizar_todas", "tw_evaluar"} <= set(tareas.REGISTRO)
    tipos = [tipo for tipo, _ in worker.PERIODICAS]
    assert tipos.index("tw_sincronizar_todas") < tipos.index("exp_refrescar_todos")
