import os

import pytest
import sqlalchemy as sa


def test_migracion_0010_sube_y_baja(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    import db
    monkeypatch.setenv("CREATV_DB_URL", f"sqlite:///{tmp_path / 'mig10.db'}")
    db._reset_para_tests()
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(raiz, "alembic.ini"))
    command.upgrade(cfg, "head")
    insp = sa.inspect(db.engine())
    assert "gasto" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("gasto")}
    assert {"cliente", "creado_en", "tipo", "usd", "proveedor", "referencia", "detalle", "extra"} <= cols
    uniques = {u["name"] for u in insp.get_unique_constraints("gasto")}
    assert "uq_gasto_referencia" in uniques
    db._reset_para_tests()
    command.downgrade(cfg, "0009")
    assert "gasto" not in sa.inspect(db.engine()).get_table_names()
    db._reset_para_tests()
    command.upgrade(cfg, "head")
    assert "gasto" in sa.inspect(db.engine()).get_table_names()
    db._reset_para_tests()


def test_registrar_es_idempotente_por_referencia(base_temporal):
    import gastos
    id1 = gastos.registrar("acme", "video", 0.5, "video:cf_1", detalle="wan3 · 5 s", proveedor="wavespeed")
    id2 = gastos.registrar("acme", "video", 0.75, "video:cf_1", detalle="wan3 · 5 s + música", extra={"musica": 0.25})
    assert id1 == id2
    filas = gastos.historial("acme")
    assert len(filas) == 1
    assert filas[0]["usd"] == 0.75 and filas[0]["detalle"] == "wan3 · 5 s + música"
    assert filas[0]["extra"] == {"musica": 0.25} and filas[0]["proveedor"] == "wavespeed"
    # otro proyecto con la misma referencia es otra fila
    gastos.registrar("otro", "video", 0.1, "video:cf_1")
    assert len(gastos.historial("otro")) == 1 and len(gastos.historial("acme")) == 1


def test_registrar_none_y_negativo_guardan_cero_y_tipo_desconocido_es_otro(base_temporal):
    import gastos
    gastos.registrar("acme", "swap", None, "swap:s1", detalle="sin tarifa")
    gastos.registrar("acme", "rarisimo", -3, "x:1")
    filas = {f["referencia"]: f for f in gastos.historial("acme")}
    assert filas["swap:s1"]["usd"] == 0.0 and filas["swap:s1"]["tipo"] == "swap"
    assert filas["x:1"]["usd"] == 0.0 and filas["x:1"]["tipo"] == "otro"
    with pytest.raises(ValueError):
        gastos.registrar("", "video", 1, "video:1")


def test_resumen_mes_por_tipo_ignora_otro_mes(base_temporal):
    import gastos
    gastos.registrar("acme", "video", 0.5, "video:a", creado_en="2026-09-03T10:00:00")
    gastos.registrar("acme", "video", 0.25, "video:b", creado_en="2026-09-10T10:00:00")
    gastos.registrar("acme", "guion", 0.02, "guion:a", creado_en="2026-09-11T10:00:00")
    gastos.registrar("acme", "video", 9.0, "video:viejo", creado_en="2026-08-30T10:00:00")
    gastos.registrar("acme", "video", 9.0, "video:futuro", creado_en="2026-09-20T10:00:00")
    gastos.registrar("otro", "video", 9.0, "video:a", creado_en="2026-09-10T10:00:00")
    r = gastos.resumen_mes("acme", ahora_iso="2026-09-18T12:00:00")
    assert r["desde"] == "2026-09-01T00:00:00" and r["hasta"] == "2026-09-18T12:00:00"
    assert r["por_tipo"] == {"video": {"usd": 0.75, "n": 2}, "guion": {"usd": 0.02, "n": 1}}
    assert r["total"] == 0.77 and r["n"] == 3


def test_historial_mas_nuevo_primero_con_limite_y_desde(base_temporal):
    import gastos
    gastos.registrar("acme", "video", 1, "video:1", creado_en="2026-09-01T10:00:00")
    gastos.registrar("acme", "video", 2, "video:2", creado_en="2026-09-05T10:00:00")
    gastos.registrar("acme", "video", 3, "video:3", creado_en="2026-09-09T10:00:00")
    assert [f["referencia"] for f in gastos.historial("acme")] == ["video:3", "video:2", "video:1"]
    assert [f["referencia"] for f in gastos.historial("acme", limite=2)] == ["video:3", "video:2"]
    assert [f["referencia"] for f in gastos.historial("acme", desde="2026-09-05T00:00:00")] == ["video:3", "video:2"]


def test_serie_diaria_rellena_dias_sin_gasto(base_temporal):
    import gastos
    gastos.registrar("acme", "video", 0.5, "video:1", creado_en="2026-09-16T10:00:00")
    gastos.registrar("acme", "video", 0.25, "video:2", creado_en="2026-09-16T18:00:00")
    gastos.registrar("acme", "guion", 0.02, "guion:1", creado_en="2026-09-18T08:00:00")
    gastos.registrar("acme", "video", 9, "video:viejo", creado_en="2026-09-14T08:00:00")
    s = gastos.serie_diaria("acme", dias=4, ahora_iso="2026-09-18T12:00:00")
    assert s == [{"dia": "2026-09-15", "usd": 0.0}, {"dia": "2026-09-16", "usd": 0.75},
                 {"dia": "2026-09-17", "usd": 0.0}, {"dia": "2026-09-18", "usd": 0.02}]


def test_por_proyecto_mes_una_consulta_y_ceros(base_temporal):
    import gastos
    gastos.registrar("acme", "video", 0.5, "video:1", creado_en="2026-09-02T10:00:00")
    gastos.registrar("acme", "final", 0.1, "final:1", creado_en="2026-09-03T10:00:00")
    gastos.registrar("beta", "video", 0.2, "video:1", creado_en="2026-09-03T10:00:00")
    gastos.registrar("beta", "video", 5, "video:viejo", creado_en="2026-08-03T10:00:00")
    assert gastos.por_proyecto_mes(["acme", "beta", "gamma"], ahora_iso="2026-09-18T00:00:00") == \
        {"acme": 0.6, "beta": 0.2, "gamma": 0.0}
    assert gastos.por_proyecto_mes([]) == {}


def test_csv_mes_con_bom_punto_y_coma_y_escape_de_formulas(base_temporal):
    import gastos
    gastos.registrar("acme", "video", 0.5, "video:1", detalle="=HYPERLINK(\"x\")", proveedor="wavespeed",
                     creado_en="2026-09-02T10:00:00")
    gastos.registrar("acme", "guion", 0.02, "guion:1", detalle="-guion", creado_en="2026-09-03T10:00:00")
    gastos.registrar("acme", "video", 9, "video:viejo", creado_en="2026-08-03T10:00:00")
    texto = gastos.csv_mes("acme", ahora_iso="2026-09-18T12:00:00")
    assert texto.startswith("﻿")
    lineas = texto.lstrip("﻿").splitlines()
    assert lineas[0] == "fecha;tipo;proveedor;referencia;detalle;usd"
    # csv entrecomilla la celda porque trae comillas; lo importante es el `'` inicial
    assert lineas[1] == '2026-09-02T10:00:00;video;wavespeed;video:1;"\'=HYPERLINK(""x"")";0,5000'
    assert lineas[2] == "2026-09-03T10:00:00;guion;;guion:1;'-guion;0,0200"
    assert len(lineas) == 3


def test_estimar_video_e_imagen_delegan_en_flowplus_modelos(monkeypatch):
    import gastos
    from providers import flowplus_modelos
    visto = {}
    monkeypatch.setattr(flowplus_modelos, "estimate_video",
                        lambda m, d, con_sonido=True: visto.update(video=(m, d, con_sonido)) or {"credits": None, "usd": 0.35})
    monkeypatch.setattr(flowplus_modelos, "estimate_imagen",
                        lambda m, n_referencias=1: visto.update(imagen=(m, n_referencias)) or {"credits": None, "usd": 0.093})
    v = gastos.estimar("video", modelo="wan3", duracion=5, con_sonido=False)
    assert v == {"usd": 0.35, "texto": "US$ 0,35 aprox.", "detalle": "wan3 · 5 s · sin sonido"}
    assert visto["video"] == ("wan3", 5.0, False)
    assert gastos.estimar("regeneracion", modelo="wan3", duracion=5)["usd"] == 0.35
    i = gastos.estimar("imagen", modelo="seedream_v5_pro", n_referencias=2)
    assert i["usd"] == 0.093 and i["texto"] == "US$ 0,09 aprox." and visto["imagen"] == ("seedream_v5_pro", 2)


def test_estimar_sin_tarifa_no_inventa(monkeypatch):
    import gastos
    from providers import flowplus_modelos

    def _boom(*a, **k):
        raise KeyError("modelo raro")
    monkeypatch.setattr(flowplus_modelos, "estimate_video", _boom)
    r = gastos.estimar("video", modelo="raro", duracion=5)
    assert r["usd"] is None and r["texto"] == "precio no disponible"
    assert gastos.estimar("video")["usd"] is None
    assert gastos.estimar("nada")["usd"] is None and gastos.estimar("nada")["texto"] == "precio no disponible"
    assert gastos.estimar("swap", proveedor="inexistente", formato="foto")["usd"] is None
    assert gastos.estimar("swap")["usd"] is None


def test_estimar_tarifas_fijas_y_final_por_pais():
    import gastos
    assert gastos.estimar("guion") == {"usd": 0.02, "texto": "US$ 0,02 aprox.", "detalle": "una llamada a Claude"}
    assert gastos.estimar("regla_producto")["usd"] == 0.01
    assert gastos.estimar("caption_organico")["usd"] == 0.01
    assert gastos.estimar("final")["usd"] == 0.10
    assert gastos.estimar("final", paises=3)["usd"] == 0.30
    assert gastos.estimar("reedicion", paises=2)["usd"] == 0.20
    assert gastos.TARIFAS["final"] == 0.10 and "final_pais_extra" not in gastos.TARIFAS


def test_estimar_swap_por_proveedor():
    import gastos
    from providers import nano_banana_client, wavespeed_imagen, kling_o1_client
    foto = gastos.estimar("swap", proveedor="nano_banana", formato="foto")
    assert foto["usd"] == nano_banana_client.COSTO_USD_POR_IMAGEN
    con_mejora = gastos.estimar("swap", proveedor="nano_banana", formato="foto", mejorar_calidad=True)
    assert con_mejora["usd"] == round(nano_banana_client.COSTO_USD_POR_IMAGEN + wavespeed_imagen.COSTO_USD_UPSCALE, 4)
    video = gastos.estimar("swap", proveedor="kling_o1", formato="video", duracion=5)
    assert video["usd"] == kling_o1_client.estimate_video(5)["usd"] and "video" in video["detalle"]
    seed = gastos.estimar("swap", proveedor="seedream_v5_pro", formato="foto", n_referencias=3)
    assert seed["usd"] == wavespeed_imagen.estimate_seedream(n_imagenes=4)["usd"]


@pytest.mark.parametrize("usd, esperado", [
    (None, "—"), (0, "US$ 0,00"), (0.005, "US$ <0,01"), (0.07, "US$ 0,07"), (0.1, "US$ 0,10"),
    (1, "US$ 1,00"), (12.4, "US$ 12,40"), (1234.567, "US$ 1.234,57"), ("abc", "—"),
])
def test_formatear(usd, esperado):
    import gastos
    assert gastos.formatear(usd) == esperado
