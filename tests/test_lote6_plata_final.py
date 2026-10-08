"""Cobros reales con SQLite aislado y fallos posteriores a respuestas pagadas."""
import copy

import pytest

import creative_flow as cf
import gastos
import materiales
import final_edition as fe
from final_edition import guion, insumos, musica, produccion, voz
from tests.test_fe_produccion import entorno, GUION_BASE
from tests.test_fe_producir import entorno as entorno_legado, clip


def falla(*args, **kwargs):
    raise RuntimeError("persistencia posterior al pago")


def gasto_unico(referencia, monto):
    filas = [g for g in gastos.historial("acme") if g["referencia"] == referencia]
    assert len(filas) == 1
    assert filas[0]["usd"] == pytest.approx(monto)
    assert gastos.historial("otro") == []
    return filas[0]


def test_pnd146_guion_antes_de_guardar(entorno, monkeypatch):
    monkeypatch.setattr(cf, "guardar_guion_base", falla)
    for _ in range(2):
        with pytest.raises(RuntimeError):
            fe.preparar_guion("acme", entorno["cf_id"], ref_sufijo=":t146")
        gasto_unico(f"guion:{entorno['cf_id']}:t146", .01)


@pytest.mark.parametrize("via", ["editor", "legado"])
@pytest.mark.parametrize("fase", ["variante", "render", "cierre"])
def test_pnd146_final_antes_de_persistir(via, fase, request, monkeypatch):
    ctx = request.getfixturevalue("entorno" if via == "editor" else "entorno_legado")
    cf_id = ctx["cf_id"]
    cf.guardar_guion_base("acme", cf_id, copy.deepcopy(GUION_BASE))
    opciones = {"con_voz": False, "con_musica": False}
    if fase == "variante":
        def variante(*a, **k):
            raise guion.GuionInvalido(["invalido"], costo_usd=.037)
        monkeypatch.setattr(guion, "variar_guion", variante)
        opciones.update(variante=1, variante_tipo="hook")
        monto = .037
    else:
        monkeypatch.setattr(guion, "localizar_guion", lambda *a, **k: (copy.deepcopy(GUION_BASE), .02))
        monto = .02
        if fase == "render":
            if via == "editor":
                from tareas import edicion
                monkeypatch.setattr(edicion, "renderizar_final", falla)
            else:
                from final_edition import render
                monkeypatch.setattr(render, "componer", falla)
    monkeypatch.setattr(cf, "actualizar_final", falla)
    ejecutar = produccion.producir if via == "editor" else fe.producir_legado
    # El editor reutiliza textos del destino base; US obliga a localizar.
    for _ in range(2):
        with pytest.raises(RuntimeError):
            ejecutar("acme", cf_id, "en", "US", opciones, ref_sufijo=":t146")
        fid = f"{cf_id}__en_US" + ("__v1" if fase == "variante" else "")
        gasto_unico(f"final:{fid}:t146", monto if via == "legado" or fase == "variante" else (.02 if _ == 0 else 0))


def test_pnd146_pista_material_falla_con_importe_y_url(entorno, monkeypatch):
    # Se usa la función de insumos real; solo el proveedor responde con un doble.
    real_musica = __import__("final_edition.insumos", fromlist=["musica"])
    import importlib
    original = importlib.util.spec_from_file_location("insumos_prueba", insumos.__file__)
    modulo = importlib.util.module_from_spec(original)
    original.loader.exec_module(modulo)
    monkeypatch.setattr(musica, "obtener_pista", lambda *a, **k: ({"archivo": "/no/existe", "url": "https://fal/p.wav"}, .02))
    monkeypatch.setattr(insumos, "musica", modulo.musica)
    for _ in range(2):
        fid, r = produccion.producir("acme", entorno["cf_id"], "es", "CO",
                                    {"con_voz": False}, ref_sufijo=":t146")
        fila = gasto_unico(f"final:{fid}:t146", .02)
        assert fila["extra"]["capas"]["musica"] == .02
        assert r["capas"]["musica"]["parametros"]["url"] == "https://fal/p.wav"


@pytest.mark.parametrize("via", ["editor", "legado"])
@pytest.mark.parametrize("bloque", [0, 1])
@pytest.mark.parametrize("fallo", ["descarga", "whisper"])
def test_pnd146_voz_pagada(via, bloque, fallo, request, monkeypatch, tmp_path):
    ctx = request.getfixturevalue("entorno" if via == "editor" else "entorno_legado")
    cf.guardar_guion_base("acme", ctx["cf_id"], copy.deepcopy(GUION_BASE))
    from providers import fal_audio
    import importlib.util
    # Los fixtures antiguos simulan la voz entera; restauramos el código probado.
    ruta = insumos.__file__ if via == "editor" else voz.__file__
    spec = importlib.util.spec_from_file_location("voz_prueba", ruta)
    modulo = importlib.util.module_from_spec(spec); spec.loader.exec_module(modulo)
    monkeypatch.setattr(insumos if via == "editor" else voz,
                        "voz_bloque" if via == "editor" else "sintetizar",
                        modulo.voz_bloque if via == "editor" else modulo.sintetizar)
    llamadas = []
    def tts(*a, **k):
        llamadas.append(a[0])
        return {"url": "https://fal/voz.mp3", "costo_usd": .05}
    monkeypatch.setattr(fal_audio, "tts", tts)
    def descargar(url, destino):
        if len(llamadas) == bloque + 1 and fallo == "descarga":
            falla()
        from pathlib import Path
        Path(destino).write_bytes(b"mp3")
        return destino
    monkeypatch.setattr(modulo, "_descargar", descargar)
    from storage import r2_uploader
    monkeypatch.setattr(r2_uploader, "upload_file", lambda *a, **k: "https://r2/voz.mp3")
    monkeypatch.setattr(modulo.cortes, "duracion", lambda *a: 1)
    def whisper(*a, **k):
        palabras = [{"inicio": object()}] if len(llamadas) == bloque + 1 and fallo == "whisper" else []
        return {"palabras": palabras, "costo_usd": .01}
    monkeypatch.setattr(fal_audio, "transcribir_palabras", whisper)
    monto = .06 * bloque + (.06 if fallo == "whisper" else .05)
    ejecutar = produccion.producir if via == "editor" else fe.producir_legado
    # Vaciar solo materiales falsos entre ejecuciones reproduce el mismo fallo y cobro;
    # el registro de gastos permanece en SQLite con la misma referencia de tarea.
    for _ in range(2):
        llamadas.clear()
        if via == "editor":
            import db, sqlalchemy as sa
            with db.transaccion() as con:
                con.execute(sa.delete(db.material))
        if bloque == 0:
            with pytest.raises(ValueError):
                ejecutar("acme", ctx["cf_id"], "es", "CO", {"con_musica": False}, ref_sufijo=":t146")
        else:
            ejecutar("acme", ctx["cf_id"], "es", "CO", {"con_musica": False}, ref_sufijo=":t146")
        fid = f"{ctx['cf_id']}__es_CO"
        gasto_unico(f"final:{fid}:t146", monto + (.02 if via == "legado" else 0))
