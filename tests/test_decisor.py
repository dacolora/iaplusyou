import pytest

import decisor

CTX = {"presupuesto_dia": 10.0, "horas_activo": 60, "atribucion": "ninguna", "posicion": 1, "total_pais": 4,
       "dias_experimento": 7, "dias_transcurridos": 3, "escalon_rescate": 0}


def snap(**kw):
    base = {"impresiones": 0, "clics_enlace": 0, "ctr": 0.0, "cpc": 0.0, "thruplay_rate": 0.0, "gasto": 0.0,
            "compras": 0, "cpa": 0.0, "roas": 0.0, "tomado_en": "2026-09-15T10:00:00"}
    base.update(kw)
    return base


def test_reglas_efectivas_capas_y_tipos():
    r = decisor.reglas_efectivas({"ctr_min": "1.5", "basura": 1}, {"cpc_max": 0.8, "n_reediciones": "2"})
    assert r["ctr_min"] == 1.5 and r["cpc_max"] == 0.8 and r["n_reediciones"] == 2
    assert "basura" not in r and r["roas_min"] == 2.0 and r["escalar_tope_dia"] is None
    assert decisor.reglas_efectivas(None, None) == decisor.REGLAS_DEFECTO


def test_sin_evidencia_queda_pendiente():
    r = decisor.reglas_efectivas(None, None)
    v = decisor.decidir([snap(impresiones=300, gasto=5.0)], r, dict(CTX, horas_activo=10))
    assert v["veredicto"] == "pendiente" and v["accion"] is None and v["puerta"] == 0
    assert "300" in v["motivo"]


def test_evidencia_por_ventana_de_horas_aunque_falten_impresiones():
    r = decisor.reglas_efectivas(None, None)
    v = decisor.decidir([snap(impresiones=300, clics_enlace=1, ctr=0.3, cpc=5.0, gasto=5.0)], r, dict(CTX, horas_activo=49))
    assert v["veredicto"] == "perdedor" and v["puerta"] == 1


def test_perdedor_por_ctr_y_rescate():
    r = decisor.reglas_efectivas(None, {"ctr_min": 1.0, "cpc_max": 0.5})
    v = decisor.decidir([snap(impresiones=2000, clics_enlace=10, ctr=0.5, cpc=0.9, gasto=25.0, thruplay_rate=0.3)], r, CTX)
    assert v["veredicto"] == "perdedor" and v["accion"] == "rescatar" and v["puerta"] == 1
    assert "ctr" in v["motivo"].lower() and v["numeros"]["ctr"] == 0.5
    v3 = decisor.decidir([snap(impresiones=2000, clics_enlace=10, ctr=0.5, cpc=0.9, gasto=25.0)], r, dict(CTX, escalon_rescate=3))
    assert v3["veredicto"] == "perdedor" and v3["accion"] == "archivar"


def test_ganador_sin_atribucion_por_trafico_y_ranking():
    r = decisor.reglas_efectivas(None, {"cpc_max": 0.5})
    ok = [snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=27.0, thruplay_rate=0.25)]
    v = decisor.decidir(ok, r, CTX)
    assert v["veredicto"] == "ganador" and v["accion"] == "escalar_y_derivar" and v["puerta"] == 1
    assert "sin ventas medibles" in v["motivo"]
    # tercio superior: con 4 anuncios solo la posición 1 gana; la 3 pasa umbrales pero sigue pendiente
    v2 = decisor.decidir(ok, r, dict(CTX, posicion=3))
    assert v2["veredicto"] == "pendiente" and "tercio" in v2["motivo"]
    # con menos de 3 anuncios en el país basta con los umbrales
    v3 = decisor.decidir(ok, r, dict(CTX, posicion=2, total_pais=2))
    assert v3["veredicto"] == "ganador"


def test_puerta_2_ventas_espera_72h_y_decide_por_roas_o_cpa():
    r = decisor.reglas_efectivas(None, {"cpc_max": 0.5, "roas_min": 2.0, "cpa_max": 8.0})
    bien = [snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=30.0, compras=5, cpa=6.0, roas=3.0, thruplay_rate=0.3)]
    ctx = dict(CTX, atribucion="pixel")
    v = decisor.decidir(bien, r, dict(ctx, horas_activo=50))
    assert v["veredicto"] == "pendiente" and v["puerta"] == 2 and "72" in v["motivo"]
    v = decisor.decidir(bien, r, dict(ctx, horas_activo=80))
    assert v["veredicto"] == "ganador" and v["puerta"] == 2 and "roas" in v["motivo"].lower()
    mal = [snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=30.0, compras=1, cpa=30.0, roas=0.5, thruplay_rate=0.3)]
    v = decisor.decidir(mal, r, dict(ctx, horas_activo=80))
    assert v["veredicto"] == "perdedor" and v["puerta"] == 2 and v["accion"] == "rescatar"


def test_thruplay_cero_es_senal_de_falla_real():
    r = decisor.reglas_efectivas(None, {"cpc_max": 0.5})
    v = decisor.decidir([snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=27.0, thruplay_rate=0.0)], r, CTX)
    assert v["veredicto"] == "perdedor" and v["puerta"] == 1
    assert "thruplay" in v["motivo"].lower()
    r2 = dict(r, cpc_max=0.5, thruplay_min=None)
    v2 = decisor.decidir([snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=27.0, thruplay_rate=0.0)], r2, CTX)
    assert v2["veredicto"] != "perdedor" or "thruplay" not in v2["motivo"].lower()


def test_inconcluso_al_cerrar_la_ventana_de_dias():
    r = decisor.reglas_efectivas(None, None)
    v = decisor.decidir([snap(impresiones=100, gasto=1.0)], r, dict(CTX, horas_activo=20, dias_transcurridos=7.5))
    assert v["veredicto"] == "inconcluso" and v["accion"] == "pausar"


def test_sin_snapshots():
    v = decisor.decidir([], decisor.REGLAS_DEFECTO, CTX)
    assert v["veredicto"] == "pendiente" and v["numeros"] == {}


def test_posicion_como_string_no_lanza_typeerror():
    r = decisor.reglas_efectivas(None, {"cpc_max": 0.5})
    ok = [snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=27.0, thruplay_rate=0.25)]
    # posición como string: debe comportarse igual que el entero equivalente.
    v = decisor.decidir(ok, r, dict(CTX, posicion="3", total_pais=4))
    assert v["veredicto"] == "pendiente" and "tercio" in v["motivo"]
    v2 = decisor.decidir(ok, r, dict(CTX, posicion="1", total_pais=4))
    assert v2["veredicto"] == "ganador"
    # posición no numérica o None: se ignora el ranking, no explota.
    v3 = decisor.decidir(ok, r, dict(CTX, posicion=None, total_pais=4))
    assert v3["veredicto"] == "ganador"
    v4 = decisor.decidir(ok, r, dict(CTX, posicion="", total_pais=4))
    assert v4["veredicto"] == "ganador"


def test_atribucion_sin_umbrales_de_venta_gana_por_trafico():
    r = decisor.reglas_efectivas(None, {"cpc_max": 0.5, "roas_min": None, "cpa_max": None})
    ok = [snap(impresiones=3000, clics_enlace=90, ctr=3.0, cpc=0.3, gasto=27.0, thruplay_rate=0.25)]
    ctx = dict(CTX, atribucion="pixel", horas_activo=80)
    v = decisor.decidir(ok, r, ctx)
    assert v["veredicto"] == "ganador" and v["accion"] == "escalar_y_derivar" and v["puerta"] == 1
    assert "sin umbrales de ventas" in v["motivo"]
    # incluso con menos de 72h de ventana de ventas: no debe quedar pendiente en puerta 2.
    v2 = decisor.decidir(ok, r, dict(ctx, horas_activo=50))
    assert v2["veredicto"] == "ganador" and v2["puerta"] == 1


def test_reglas_efectivas_permite_desactivar_umbrales_con_none_o_vacio():
    r = decisor.reglas_efectivas({"ctr_min": None, "roas_min": ""}, None)
    assert r["ctr_min"] is None and r["roas_min"] is None
    # los umbrales por defecto ya None siguen apagables (sin cambios de comportamiento).
    r2 = decisor.reglas_efectivas(None, {"cpc_max": 0.8, "escalar_tope_dia": 50})
    r3 = decisor.reglas_efectivas(r2, {"cpc_max": None, "escalar_tope_dia": ""})
    assert r3["cpc_max"] is None and r3["escalar_tope_dia"] is None
    # claves no-umbral con valor vacío/None conservan el valor de la capa anterior.
    r4 = decisor.reglas_efectivas({"ventana_horas": 72}, {"ventana_horas": None, "impresiones_min": ""})
    assert r4["ventana_horas"] == 72 and r4["impresiones_min"] == decisor.REGLAS_DEFECTO["impresiones_min"]


def test_reglas_defecto_por_proyecto(tmp_path, monkeypatch):
    import proyectos
    monkeypatch.setattr(proyectos, "_path", lambda cliente: str(tmp_path / f"{cliente}.json"))
    assert proyectos.reglas_defecto("acme") == {}
    proyectos.guardar_reglas_defecto("acme", {"ctr_min": 1.2, "basura": 9})
    assert proyectos.reglas_defecto("acme") == {"ctr_min": 1.2}
