"""El presupuesto de «Nuevo experimento» (spec 2026-10-02 §5.1–§5.3): total + días → diario por país, atajos,
validación del servidor y la paridad Python↔JS de la cuenta. Plata: cada prueba falla si se rompe la regla que nombra."""
import json
import os
import random
import re
import shutil
import subprocess

import pytest

import presupuesto_experimentos as pe

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NODE = shutil.which("node")


# ---------- repartir ----------

def test_el_diario_de_cada_pais_es_su_parte_de_anuncios_entre_los_dias_redondeado_hacia_abajo():
    # 300.000 COP en 7 días, 4 anuncios en CO y 2 en MX: 300000 × 4/6 / 7 = 28571,4 → 28571 (sin decimales: COP)
    r = pe.repartir(300000, 7, {"CO": 4, "MX": 2}, "COP")
    assert r["presupuestos"] == {"CO": 28571.0, "MX": 14285.0}
    # nunca se pasa del total: es lo que hace verdad «Máximo que puede gastar»
    assert r["total_repartido"] == (28571 + 14285) * 7 == 299992 and r["total_repartido"] <= 300000
    # USD lleva centavos: 100 USD en 7 días, 3 anuncios en un país → 14,2857 → 14,28
    assert pe.repartir(100, 7, {"US": 3}, "USD")["presupuestos"] == {"US": 14.28}
    # una moneda sin decimales (CLP) redondea a la unidad
    assert pe.repartir(1000000, 3, {"CL": 1, "AR": 2}, "CLP")["presupuestos"] == {"CL": 111111.0, "AR": 222222.0}


def test_el_reparto_nunca_supera_el_total_en_ningun_caso_al_azar():
    azar = random.Random(20261003)
    for _ in range(400):
        moneda = azar.choice(["COP", "USD", "CLP", "MXN", "EUR", "JPY", "BRL"])
        paises = {p: azar.randint(1, 9) for p in azar.sample(["CO", "MX", "US", "ES", "CL"], azar.randint(1, 4))}
        total, dias = round(azar.uniform(1, 5_000_000), azar.choice([0, 2])), azar.randint(1, 30)
        r = pe.repartir(total, dias, paises, moneda)
        assert r["total_repartido"] <= total + 1e-6, (moneda, paises, total, dias, r)


def test_un_pais_bajo_el_minimo_de_meta_se_dice_y_el_total_minimo_lo_arregla_justo():
    # Mínimo de COP: 4.000 al día. 60.000 en 7 días con 1 anuncio en CO y 5 en MX: CO queda en 1.428 < 4.000.
    r = pe.repartir(60000, 7, {"CO": 1, "MX": 5}, "COP")
    assert r["bajos"] == ["CO"]
    arreglado = pe.repartir(r["total_minimo"], 7, {"CO": 1, "MX": 5}, "COP")
    assert arreglado["bajos"] == [] and arreglado["presupuestos"]["CO"] >= 4000
    # ... y es el MÁS CHICO que lo arregla: una unidad menos y vuelve a quedar bajo
    assert pe.repartir(r["total_minimo"] - 1, 7, {"CO": 1, "MX": 5}, "COP")["bajos"] == ["CO"]
    # lo mismo con centavos
    r = pe.repartir(10, 7, {"US": 1, "ES": 4}, "USD")
    assert r["bajos"] == ["US"]
    assert pe.repartir(r["total_minimo"], 7, {"US": 1, "ES": 4}, "USD")["bajos"] == []
    assert pe.repartir(r["total_minimo"] - 0.01, 7, {"US": 1, "ES": 4}, "USD")["bajos"] == ["US"]


def test_un_total_alcanza_si_todos_los_paises_estan_en_el_minimo_o_mas():
    assert pe.repartir(1000000, 7, {"CO": 1, "MX": 1}, "COP")["bajos"] == []


@pytest.mark.parametrize("total,dias,paises", [(0, 7, {"CO": 1}), (-5, 7, {"CO": 1}), (float("nan"), 7, {"CO": 1}),
                                               (float("inf"), 7, {"CO": 1}), (100, 0, {"CO": 1}), (100, 91, {"CO": 1}),
                                               (100, 2.5, {"CO": 1}), (100, 7, {}), (100, 7, {"CO": 0}),
                                               (100, 7, {"CO": 1.5})])
def test_repartir_rechaza_lo_que_no_tiene_sentido(total, dias, paises):
    with pytest.raises(pe.ErrorPresupuesto):
        pe.repartir(total, dias, paises, "COP")


# ---------- atajos ----------

def test_los_atajos_son_4_8_y_15_veces_el_minimo_por_anuncio_en_4_7_y_10_dias_a_dos_cifras():
    # 6 anuncios en COP (mínimo 4.000): 6×4000×4×4 = 384.000 → 390.000; ×8×7 = 1.344.000 → 1.400.000; ×15×10 = 3.600.000
    assert pe.atajos("COP", {"CO": 3, "MX": 3}) == [{"total": 390000.0, "dias": 4}, {"total": 1400000.0, "dias": 7},
                                                     {"total": 3600000.0, "dias": 10}]
    # 1 anuncio en USD (mínimo 1): 16, 56, 150
    assert pe.atajos("USD", {"US": 1}) == [{"total": 16.0, "dias": 4}, {"total": 56.0, "dias": 7}, {"total": 150.0, "dias": 10}]
    # una moneda sin mínimo conocido usa 1, como el resto del código
    assert pe.atajos("GBP", {"UK": 2})[1] == {"total": 120.0, "dias": 7}      # 2×1×8×7 = 112 → 120 (2 cifras)


def test_ningun_atajo_deja_un_pais_bajo_el_minimo():
    azar = random.Random(7)
    for _ in range(200):
        moneda = azar.choice(sorted(pe.PRESUPUESTO_MINIMO_DIARIO))
        paises = {p: azar.randint(1, 8) for p in azar.sample(["CO", "MX", "US", "ES", "CL"], azar.randint(1, 4))}
        for a in pe.atajos(moneda, paises):
            assert pe.repartir(a["total"], a["dias"], paises, moneda)["bajos"] == [], (moneda, paises, a)


# ---------- validar (la comprobación del servidor) ----------

def test_validar_acepta_un_reparto_que_cabe_en_el_total():
    pe.validar("300000", 7, ["28571", "14285"], "COP")
    pe.validar("100", 7, ["14.28"], "USD")
    pe.validar("1400", 7, ["200"], "USD")                  # justo en el total


def test_validar_rechaza_el_reparto_que_supera_el_total_con_un_uno_por_ciento_de_margen():
    # 2 países × 20.000 × 7 días = 280.000
    pe.validar("280000", 7, ["20000", "20000"], "COP")
    pe.validar("277500", 7, ["20000", "20000"], "COP")     # 280.000 ≤ 277.500 × 1,01 = 280.275: dentro del margen
    for total in ("277000", "100000", "1"):
        with pytest.raises(pe.ErrorPresupuesto) as e:
            pe.validar(total, 7, ["20000", "20000"], "COP")
        assert e.value.codigo == "total", total
    # y el margen es solo un uno por ciento, no más
    with pytest.raises(pe.ErrorPresupuesto):
        pe.validar("270000", 7, ["20000", "20000"], "COP")


def test_validar_sigue_pidiendo_el_minimo_los_decimales_de_la_moneda_y_numeros_de_verdad():
    casos = [("minimo", ("500000", 7, ["3999"], "COP")), ("precision", ("500000", 7, ["4000.5"], "COP")),
             ("precision", ("500", 7, ["10.001"], "USD")), ("numero", ("nan", 7, ["4000"], "COP")),
             ("numero", ("inf", 7, ["4000"], "COP")), ("numero", ("-1", 7, ["4000"], "COP")),
             ("numero", ("500000", 7, ["abc"], "COP")), ("numero", ("500000", 7, [None], "COP")),
             ("dias", ("500000", 0, ["4000"], "COP")), ("dias", ("500000", 91, ["4000"], "COP")),
             ("dias", ("500000", 2.5, ["4000"], "COP")), ("paises", ("500000", 7, [], "COP"))]
    for codigo, args in casos:
        with pytest.raises(pe.ErrorPresupuesto) as e:
            pe.validar(*args)
        assert e.value.codigo == codigo, (codigo, args)


# ---------- un solo lugar ----------

def test_el_minimo_diario_de_meta_vive_en_un_solo_lugar_y_dashboard_lo_importa():
    definiciones = []
    for carpeta, dirs, archivos in os.walk(RAIZ):
        dirs[:] = [d for d in dirs if d not in {"venv", ".git", ".claude", "node_modules", "__pycache__", ".superpowers"}]
        for nombre in archivos:
            if nombre.endswith(".py") and nombre != "test_presupuesto_experimentos.py":
                with open(os.path.join(carpeta, nombre), encoding="utf-8") as f:
                    if re.search(r"^PRESUPUESTO_MINIMO_DIARIO\s*=\s*\{", f.read(), re.M):
                        definiciones.append(os.path.relpath(os.path.join(carpeta, nombre), RAIZ))
    assert definiciones == ["presupuesto_experimentos.py"], definiciones
    import dashboard
    assert dashboard.PRESUPUESTO_MINIMO_DIARIO is pe.PRESUPUESTO_MINIMO_DIARIO


def test_las_monedas_sin_decimales_son_las_que_lanzador_manda_a_meta_sin_multiplicar():
    from tareas.meta import MONEDAS_SIN_DECIMALES
    import lanzador
    assert pe.SIN_DECIMALES == set(MONEDAS_SIN_DECIMALES)
    # lo que se muestra con 2 decimales se manda ×100; lo que no, tal cual
    assert lanzador.centavos(14.28, "USD") == 1428 and lanzador.centavos(111111, "CLP") == 111111


def test_el_js_copia_las_mismas_monedas_y_atajos_que_python():
    js = open(os.path.join(RAIZ, "static", "presupuesto_exp.js"), encoding="utf-8").read()
    monedas = re.search(r"var EN_ENTEROS = (\[.*?\]);", js, re.S).group(1).replace("'", '"')
    assert set(json.loads(monedas)) == pe.EN_ENTEROS
    atajos = re.search(r"var ATAJOS = (\[\[.*?\]\]);", js, re.S).group(1)
    assert json.loads(atajos) == [list(a) for a in pe.ATAJOS]


# ---------- paridad Python ↔ JS ----------

_ARNES = r"""
const fs = require('fs');
const P = require(process.argv[1]);
const casos = JSON.parse(fs.readFileSync(0, 'utf8'));
console.log(JSON.stringify(casos.map((c) => ({
  repartir: P.repartir(c.total, c.dias, c.pesos, c.moneda, c.minimo),
  atajos: P.atajos(c.pesos, c.minimo),
}))));
"""

CASOS_FIJOS = [
    (300000, 7, {"CO": 4, "MX": 2}, "COP"), (300000, 7, {"CO": 3, "MX": 3}, "COP"), (100, 7, {"US": 3}, "USD"),
    (1000000, 3, {"CL": 1, "AR": 2}, "CLP"), (60000, 7, {"CO": 1, "MX": 5}, "COP"),     # un país bajo el mínimo
    (10, 7, {"US": 1, "ES": 4}, "USD"), (1.15, 1, {"US": 1}, "USD"), (0.29, 1, {"US": 1}, "USD"),
    (123.45, 9, {"US": 2, "ES": 1, "MX": 3}, "USD"), (5000000, 10, {"CO": 7, "MX": 1, "PE": 1}, "COP"),
    (20, 1, {"MX": 1}, "MXN"), (99.99, 30, {"BR": 2, "AR": 5}, "BRL"), (1500, 5, {"JP": 1, "KR": 2}, "JPY"),
    (1000, 4, {"CO": 1, "MX": 1, "US": 1}, "COP"), (4000, 1, {"CO": 1}, "COP"), (3999, 1, {"CO": 1}, "COP"),
    (7, 3, {"US": 1, "ES": 2}, "EUR"), (0.07, 7, {"US": 1}, "USD"),
]


def _casos_al_azar(n):
    azar = random.Random(20261003)
    casos = []
    for _ in range(n):
        moneda = azar.choice(["COP", "USD", "CLP", "MXN", "EUR", "JPY", "BRL", "PEN", "ARS", "GBP"])
        paises = {p: azar.randint(1, 9) for p in azar.sample(["CO", "MX", "US", "ES", "CL"], azar.randint(1, 3))}
        total = round(azar.uniform(0.5, 9_000_000), azar.choice([0, 1, 2, 3]))
        casos.append((total, azar.randint(1, 90), paises, moneda))
    return casos


@pytest.mark.skipif(not NODE, reason="sin Node no se corre el JS (el VPS no lo tiene)")
def test_el_reparto_y_los_atajos_en_js_dan_lo_mismo_que_en_python():
    casos = CASOS_FIJOS + _casos_al_azar(600)
    entrada = [{"total": t, "dias": d, "pesos": p, "moneda": m, "minimo": pe.PRESUPUESTO_MINIMO_DIARIO.get(m, 1)}
               for t, d, p, m in casos]
    r = subprocess.run([NODE, "-e", _ARNES, os.path.join(RAIZ, "static", "presupuesto_exp.js")], input=json.dumps(entrada),
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    js = json.loads(r.stdout)
    assert len(js) == len(casos)
    for (total, dias, paises, moneda), salida in zip(casos, js):
        esperado = pe.repartir(total, dias, paises, moneda)
        assert salida["repartir"] == esperado, (total, dias, paises, moneda)
        assert salida["atajos"] == pe.atajos(moneda, paises), (moneda, paises)


@pytest.mark.skipif(not NODE, reason="sin Node no se corre el JS (el VPS no lo tiene)")
def test_la_paridad_cubre_un_pais_bajo_el_minimo_y_cada_tipo_de_moneda():
    # La prueba de arriba no vale si los casos no tocan lo difícil: se comprueba que sí lo tocan.
    bajos = [c for c in CASOS_FIJOS if pe.repartir(*c[:3], c[3])["bajos"]]
    assert len(bajos) >= 3
    assert {c[3] for c in CASOS_FIJOS} >= {"COP", "USD", "CLP", "MXN", "JPY"}
    assert {len(c[2]) for c in CASOS_FIJOS} == {1, 2, 3}
