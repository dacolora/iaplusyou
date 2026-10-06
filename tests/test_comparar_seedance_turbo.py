"""comparar_seedance_turbo.py: regenerar con el acceso Turbo de WaveSpeed una
pieza de Seedance 2.5 ya hecha, con las MISMAS entradas (solo cambia la ruta),
sin cobrar nada hasta que la persona escriba «si», y anotando lo que se pagó."""
import pytest
import sqlalchemy as sa

import comparar_seedance_turbo as cst
import creative_flow as cf
import db
from providers import flowplus_modelos, wavespeed_common


def _gastos(cliente="acme"):
    with db.conectar() as con:
        return [dict(f._mapping) for f in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente))]


def _pieza(modelo="seedance25", estado="video_listo", refs=("https://x/1.png",), duracion=8, **campos):
    cid = cf.crear("acme", [], [], [], "camina por la playa", duracion, "", "A", referencias_urls=list(refs))
    base = dict(estado=estado, tipo="video", modelo=modelo, prompt_relleno="Una mujer camina con @Imagen 1",
                aspect_ratio="9:16", video_url=f"https://r2/{modelo}.mp4", usd=round(0.36 * duracion, 3))
    base.update(campos)
    cf.actualizar("acme", cid, **base)
    return cid


def _lo_que_manda_seedance(monkeypatch, cid):
    """Lo que generar_video le mandaría a Seedance 2.5 con lo que prepara el worker."""
    from tareas import flowplus
    entry, refs, _v, duracion, prompt, _p, ar, modelo, calidad = flowplus._preparar("acme", cid)
    vistos = []
    monkeypatch.setattr(flowplus_modelos, "_lanzar", lambda path, payload, nombre, **k: vistos.append((path, payload)))
    flowplus_modelos.generar_video(modelo, prompt, refs, duracion, aspect_ratio=ar,
                                   con_sonido=entry.get("con_sonido", True) is not False, calidad=calidad)
    monkeypatch.undo()
    return vistos[0]


@pytest.fixture()
def entorno(base_temporal, monkeypatch, tmp_path):
    monkeypatch.setattr(cst, "BASE_DIR", str(tmp_path))
    subidos = {}

    def _subir(local, key, content_type):
        subidos[key] = open(local, encoding="utf-8").read() if content_type.startswith("text/html") else local
        return f"https://r2/{key}"
    monkeypatch.setattr(cst.r2_uploader, "upload_file", _subir)
    monkeypatch.setattr(cst, "_bajar", lambda url, destino: open(destino, "wb").write(b"mp4"))
    return {"subidos": subidos, "tmp": tmp_path}


def test_con_imagen_turbo_recibe_lo_mismo_que_seedance(entorno, monkeypatch):
    cid = _pieza(duracion=8)
    path, payload = _lo_que_manda_seedance(monkeypatch, cid)
    e = cst.entradas("acme", cid)
    assert path == "bytedance/seedance-2.5/image-to-video" and e["path"] == path + "-turbo" == cst.PATH_TURBO
    assert e["payload"] == payload and payload["image"] == "https://x/1.png" and payload["resolution"] == "720p"
    assert e["duracion"] == 8 and e["usd_turbo"] == 1.6 and e["usd_original"] == 2.88


def test_solo_texto_turbo_recibe_lo_mismo_que_seedance(entorno, monkeypatch):
    cid = _pieza(refs=(), duracion=10, aspect_ratio="16:9", con_sonido=False)
    path, payload = _lo_que_manda_seedance(monkeypatch, cid)
    e = cst.entradas("acme", cid)
    assert path == "bytedance/seedance-2.5/text-to-video" and e["path"] == path + "-turbo" == cst.PATH_TEXTO_TURBO
    assert e["payload"] == payload and payload["aspect_ratio"] == "16:9" and payload["generate_audio"] is False
    assert e["usd_turbo"] == 2.0


def test_candidatas_son_solo_videos_de_seedance_terminados_y_los_mas_nuevos_primero(entorno):
    viejo = _pieza(duracion=5)
    _pieza(estado="video_generando")
    _pieza(modelo="wan3")
    _pieza(tipo="imagen")
    nuevo = _pieza(duracion=12)
    lista = cst.candidatas("acme")
    assert [c["cf_id"] for c in lista] == [nuevo, viejo]
    assert lista[0]["usd_turbo"] == 2.4 and lista[0]["con_imagen"] is True


@pytest.mark.parametrize("campos, motivo", [
    ({"modelo": "wan3"}, "no es de Seedance"),
    ({"estado": "video_generando"}, "no es un video terminado"),
    ({"tipo": "imagen"}, "no es un video terminado"),
    ({"imagen_inicial": "https://x/f.jpg"}, "cadena"),
])
def test_no_compara_lo_que_no_es_un_video_de_seedance_terminado(entorno, campos, motivo):
    cid = _pieza(**campos)
    with pytest.raises(cst.PiezaNoComparable, match=motivo):
        cst.entradas("acme", cid)
    with pytest.raises(cst.PiezaNoComparable, match="no existe"):
        cst.entradas("acme", "no-existe")


def _sin_lanzar(*a, **k):
    raise AssertionError("no debía llamar a WaveSpeed")


def test_listar_y_ver_el_total_no_cobran_nada(entorno, monkeypatch, capsys):
    cid = _pieza(duracion=8)
    monkeypatch.setattr(flowplus_modelos, "_lanzar", _sin_lanzar)
    assert cst.main(["--cliente", "acme"]) == 0
    assert cid in capsys.readouterr().out
    assert cst.main(["--cliente", "acme", "--cf", cid]) == 0
    salida = capsys.readouterr().out
    assert "Total: US$ 1.60" in salida and "Nada se generó" in salida
    assert _gastos() == [] and entorno["subidos"] == {}


def test_sin_escribir_si_no_genera(entorno, monkeypatch):
    cid = _pieza()
    monkeypatch.setattr(flowplus_modelos, "_lanzar", _sin_lanzar)
    preguntas = []
    assert cst.main(["--cliente", "acme", "--cf", cid, "--generar"],
                    preguntar=lambda t: preguntas.append(t) or "no") == 1
    assert "US$ 2.88" not in preguntas[0] and "US$ 1.60" in preguntas[0]
    assert _gastos() == [] and entorno["subidos"] == {}


def test_mas_de_cinco_piezas_no_se_aceptan(entorno, monkeypatch):
    ids = [_pieza() for _ in range(6)]
    monkeypatch.setattr(flowplus_modelos, "_lanzar", _sin_lanzar)
    args = ["--cliente", "acme", "--generar"] + [x for cid in ids for x in ("--cf", cid)]
    assert cst.main(args, preguntar=lambda t: "si") == 2
    assert _gastos() == []


def test_genera_anota_el_gasto_sube_el_video_y_la_pagina(entorno, monkeypatch):
    a, b = _pieza(duracion=8), _pieza(refs=(), duracion=5)
    llamadas = []

    def _lanzar(path, payload, nombre, on_progreso=None, **k):
        llamadas.append((path, payload["duration"]))
        on_progreso({"fase": "created", "elapsed": 0, "prediction_id": f"p{len(llamadas)}"})
        return f"https://ws/{len(llamadas)}.mp4"
    monkeypatch.setattr(flowplus_modelos, "_lanzar", _lanzar)
    assert cst.main(["--cliente", "acme", "--cf", a, "--cf", b, "--generar"], preguntar=lambda t: "Sí") == 0
    assert llamadas == [(cst.PATH_TURBO, 8), (cst.PATH_TEXTO_TURBO, 5)]
    g = sorted(_gastos(), key=lambda x: x["usd"], reverse=True)
    assert [(x["tipo"], x["usd"]) for x in g] == [("video", 1.6), ("video", 1.0)]
    assert g[0]["referencia"].startswith(f"turbo:{a}:") and g[1]["referencia"].startswith(f"turbo:{b}:")
    videos = [k for k in entorno["subidos"] if k.endswith(".mp4")]
    assert sorted(videos) == sorted(k for k in videos if k.startswith("clientes/acme/comparaciones/seedance_turbo/"))
    html = next(v for k, v in entorno["subidos"].items() if k.endswith("index.html"))
    assert "https://r2/seedance25.mp4" in html and f"/{a}.mp4" in html and f"/{b}.mp4" in html
    assert "US$ 2.88" in html and "US$ 1.60" in html and "camina" not in html.split("<body>")[0]


def test_una_espera_agotada_anota_el_gasto_y_un_rechazo_no(entorno, monkeypatch):
    a, b = _pieza(duracion=8), _pieza(duracion=5)

    def _lanzar(path, payload, nombre, on_progreso=None, **k):
        if payload["duration"] == 8:
            raise wavespeed_common.EsperaAgotada(nombre, "pred-123", 1200)
        raise wavespeed_common.ErrorProveedor(nombre, "failed", detalle="contenido sensible", codigo="1200",
                                             prediction_id="pred-9")
    monkeypatch.setattr(flowplus_modelos, "_lanzar", _lanzar)
    assert cst.main(["--cliente", "acme", "--cf", a, "--cf", b, "--generar"], preguntar=lambda t: "si") == 1
    g = _gastos()
    assert len(g) == 1 and g[0]["usd"] == 1.6 and "pred-123" in g[0]["detalle"]
    html = next(v for k, v in entorno["subidos"].items() if k.endswith("index.html"))
    assert "pred-123" in html and "contenido sensible" in html
