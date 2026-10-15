"""PND-314 (decisión 2026-10-13, lote 1): si una final falla después de pagar, el guion base se revierte y voz,
Whisper y localización quedan `no_cobrado`, pero todo queda en caché y la siguiente producción lo reusaba a
US$ 0: esa parte nunca se cobraba. Ahora se cobra cuando se reusa (el costo pasa a la final que sí se entrega)."""
import pytest
import sqlalchemy as sa

import db
from tests.test_fe_produccion import entorno  # noqa: F401 — el mismo entorno falso de la producción

pytestmark = pytest.mark.usefixtures("margen_1_5")


def _render_que_falla(monkeypatch):
    import tareas.edicion as te

    def _revienta(*a, **k):
        raise RuntimeError("ffmpeg murió")
    monkeypatch.setattr(te, "renderizar_final", _revienta)


def _render_que_anda(monkeypatch):
    import tareas.edicion as te
    monkeypatch.setattr(te, "renderizar_final", lambda c, fid, vid, i, p, avisar=None: {
        "url_video": "https://r2/v.mp4", "url_miniatura": "https://r2/v.png", "duracion_s": 8.0, "tramos": 1,
        "con_ass": True, "version_id": vid, "es_imagen": False})


def _filas():
    import gastos
    return {f["referencia"]: f for f in gastos.historial("acme")}


def _cobrado_de(ref):
    g, m = db.gasto, db.movimiento_saldo
    with db.conectar() as con:
        gid = con.execute(sa.select(g.c.id).where(g.c.cliente == "acme", g.c.referencia == ref)).scalar()
        return -sum(r.milesimas for r in con.execute(sa.select(m.c.milesimas).where(m.c.gasto_id == gid)))


def _total_gasto():
    with db.conectar() as con:
        return round(con.execute(sa.select(sa.func.sum(db.gasto.c.usd)).where(db.gasto.c.cliente == "acme")).scalar(), 4)


def _producir(n, *args, **kw):
    """Como el worker: dentro de su trabajo, y si falla, revierte los cobros de esa tarea."""
    from cobros import libro
    from final_edition import produccion
    with libro.en_trabajo(n, f"job-{n}"):
        try:
            return produccion.producir("acme", *args, ref_sufijo=f":t{n}", **kw)
        except Exception:
            libro.revertir_trabajo("acme", f"job-{n}", "falló", desde_tarea=n)
            raise


def test_lo_que_dejo_una_final_fallida_se_cobra_en_la_que_lo_reusa(entorno, monkeypatch):
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    cf_id = entorno["cf_id"]
    _render_que_falla(monkeypatch)
    with pytest.raises(RuntimeError):
        _producir(1, cf_id, "es", "CO", {})
    f = _filas()
    assert f[f"final:{cf_id}__es_CO:t1"]["usd"] == pytest.approx(0.27)
    assert _cobrado_de(f"final:{cf_id}__es_CO:t1") == 0 and _cobrado_de(f"guion:{cf_id}:t1") == 0   # nada cobrado
    total = _total_gasto()

    _render_que_anda(monkeypatch)
    _, r = _producir(2, cf_id, "es", "CO", {})
    assert r["estado"] == "listo" and r["costo_usd"] == 0.0           # no se le pagó nada nuevo al proveedor
    f = _filas()
    nueva = f[f"final:{cf_id}__es_CO:t2"]
    assert nueva["usd"] == pytest.approx(0.27 + 0.01)                 # borrador (voz + música) + guion base
    assert _cobrado_de(f"final:{cf_id}__es_CO:t2") == libro.precio_milesimas(0.28, 1.5)
    assert f[f"final:{cf_id}__es_CO:t1"]["usd"] == 0 and f[f"guion:{cf_id}:t1"]["usd"] == 0
    assert _total_gasto() == total                                     # el proveedor cobró una vez, se anota una vez

    # Reproducirla otra vez no vuelve a cobrar lo mismo.
    _producir(3, cf_id, "es", "CO", {})
    assert _filas()[f"final:{cf_id}__es_CO:t3"]["usd"] == 0.0


def test_la_traduccion_de_un_destino_fallido_se_cobra_al_reusarla(entorno, monkeypatch):
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    cf_id = entorno["cf_id"]
    _producir(1, cf_id, "es", "CO", {"precio": 89900})                 # el base, entregado
    _render_que_falla(monkeypatch)
    with pytest.raises(RuntimeError):
        _producir(2, cf_id, "en", "US", {"precios": {"en_US": 24.99}})
    assert _filas()[f"final:{cf_id}__en_US:t2"]["usd"] == pytest.approx(0.27)   # localización + voz en inglés
    _render_que_anda(monkeypatch)
    _producir(3, cf_id, "en", "US", {"precios": {"en_US": 24.99}})
    f = _filas()
    assert f[f"final:{cf_id}__en_US:t3"]["usd"] == pytest.approx(0.27)
    assert f[f"final:{cf_id}__en_US:t2"]["usd"] == 0
    assert _cobrado_de(f"final:{cf_id}__en_US:t3") == libro.precio_milesimas(0.27, 1.5)
    # Lo del destino en inglés no se le carga a otro destino que no lo usa.
    _producir(4, cf_id, "es", "CO", {"precio": 89900})
    assert _filas()[f"final:{cf_id}__es_CO:t4"]["usd"] == 0.0


def test_un_proyecto_que_no_cobra_no_mueve_nada(entorno, monkeypatch):
    cf_id = entorno["cf_id"]
    _render_que_falla(monkeypatch)
    with pytest.raises(RuntimeError):
        _producir(1, cf_id, "es", "CO", {})
    _render_que_anda(monkeypatch)
    _producir(2, cf_id, "es", "CO", {})
    f = _filas()
    assert f[f"final:{cf_id}__es_CO:t1"]["usd"] == pytest.approx(0.27)
    assert f[f"final:{cf_id}__es_CO:t2"]["usd"] == 0.0


def test_la_voz_de_audios_que_quedo_de_un_audio_fallido_se_cobra_al_reusarla(base_temporal, monkeypatch):
    """«Igual, por centavos, `audio_generar` si falla la mezcla»: la voz cruda queda en caché y se reusa gratis."""
    import audios
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    monkeypatch.setattr(audios, "sintetizar", lambda c, voz, texto, idioma, vel: {
        "url": "https://fal/v.mp3", "costo_usd": 0.012, "proveedor": "fal/elevenlabs", "etiqueta": "x",
        "voz_nombre": voz})
    monkeypatch.setattr(audios, "descargar_url", lambda url, destino: (open(destino, "wb").write(b"MP3"), destino)[1])
    monkeypatch.setattr(audios.r2_uploader, "upload_file", lambda local, key, ct: "https://r2/" + key)
    monkeypatch.setattr(audios.cortes, "duracion", lambda ruta: 2.0)
    with libro.en_trabajo(1, "job-a1"):
        audios.voz_cruda("acme", "Hola a todos", "Rachel", "es", "normal", ":t1")
    libro.revertir_trabajo("acme", "job-a1", "falló la mezcla", desde_tarea=1)
    with libro.en_trabajo(2, "job-a2"):
        _, creada = audios.voz_cruda("acme", "Hola a todos", "Rachel", "es", "normal", ":t2")
    assert creada is False
    f = _filas()
    (ref1,) = [r for r in f if r.endswith(":t1")]
    (ref2,) = [r for r in f if r.endswith(":t2")]
    assert f[ref1]["usd"] == 0 and f[ref2]["usd"] == pytest.approx(0.012)
    assert _cobrado_de(ref2) == libro.precio_milesimas(0.012, 1.5)


def test_un_guion_reescrito_no_cobra_la_version_vieja(entorno, monkeypatch):
    """Revisión de guardian-gasto: la clave del guion base va por versión. Si el guion se reescribió después de la
    final fallida, la que se entrega no cobra el viejo que nadie reusó."""
    import copy

    import creative_flow as cf
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    cf_id = entorno["cf_id"]
    _render_que_falla(monkeypatch)
    with pytest.raises(RuntimeError):
        _producir(1, cf_id, "es", "CO", {})
    nuevo = copy.deepcopy(cf.guion_base("acme", cf_id))
    nuevo["bloques"][0]["texto_voz"] = "Otro arranque"
    cf.guardar_guion_base("acme", cf_id, nuevo)
    _render_que_anda(monkeypatch)
    _producir(2, cf_id, "es", "CO", {})
    f = _filas()
    assert f[f"guion:{cf_id}:t1"]["usd"] == pytest.approx(0.01)      # el viejo no se movió ni se cobró
    nueva = f[f"final:{cf_id}__es_CO:t2"]
    # Guion nuevo, borrador nuevo: solo paga la voz del bloque que cambió y no se lleva nada del intento fallido.
    assert nueva["usd"] == pytest.approx(0.05) and not (nueva["extra"] or {}).get("traslados")
    assert f[f"final:{cf_id}__es_CO:t1"]["usd"] == pytest.approx(0.27)


def test_una_final_fallida_con_borrador_y_destino_se_cobra_una_sola_vez(entorno, monkeypatch):
    """Revisión de guardian-gasto: la primera final de un destino que no es el del guion base crea el borrador Y
    traduce el destino; si falla, su fila trae las dos claves. La que se entrega cobra las dos, una sola vez."""
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    cf_id = entorno["cf_id"]
    _render_que_falla(monkeypatch)
    with pytest.raises(RuntimeError):
        _producir(1, cf_id, "en", "US", {"precios": {"en_US": 24.99}})
    fallida = _filas()[f"final:{cf_id}__en_US:t1"]
    assert fallida["usd"] == pytest.approx(0.54) and len(fallida["extra"]["cache"]) == 2
    total = _total_gasto()
    _render_que_anda(monkeypatch)
    _producir(2, cf_id, "en", "US", {"precios": {"en_US": 24.99}})
    f = _filas()
    assert f[f"final:{cf_id}__en_US:t2"]["usd"] == pytest.approx(0.54 + 0.01)
    assert f[f"final:{cf_id}__en_US:t1"]["usd"] == 0
    with db.conectar() as con:
        neto = -con.execute(sa.select(sa.func.sum(db.movimiento_saldo.c.milesimas))).scalar()
    assert neto == libro.precio_milesimas(0.55, 1.5) and _total_gasto() == total


def test_la_voz_que_no_se_pudo_subir_no_queda_marcada_para_cobrarse(base_temporal, monkeypatch):
    """Revisión de guardian-gasto: la marca de caché de la voz va DESPUÉS de bajarla y subirla; si eso falla, no hay
    nada que reusar y otra tarea que la vuelva a pagar no carga con el intento fallido."""
    import audios
    import gastos
    from cobros import libro
    libro.configurar("acme", usuario="admin", cobrar=True)
    monkeypatch.setattr(audios, "sintetizar", lambda c, voz, texto, idioma, vel: {
        "url": "https://fal/v.mp3", "costo_usd": 0.012, "proveedor": "fal/elevenlabs", "etiqueta": "x",
        "voz_nombre": voz})
    monkeypatch.setattr(audios, "descargar_url", lambda url, destino: (_ for _ in ()).throw(RuntimeError("red")))
    with libro.en_trabajo(1, "job-a1"), pytest.raises(RuntimeError):
        audios.voz_cruda("acme", "Hola a todos", "Rachel", "es", "normal", ":t1")
    libro.revertir_trabajo("acme", "job-a1", "falló", desde_tarea=1)
    (fila,) = _filas().values()
    assert not (fila["extra"] or {}).get("cache")
    assert gastos.pendientes_por_clave("acme", ("locucion:",), {k for k in ["voz:x"]}) == []
