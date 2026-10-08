import pytest

from tests.test_tablero import _snap, _experimento, _pieza_en, sin_red, AHORA  # noqa: F401
from tests.test_tareas_flowplus import _sesion_video, _fakes_de_cierre, _estado_en_tmp  # noqa: F401


# ---------- PND-125: el worker muere mezclando, ya pagada la pista ----------
def test_sonda125_muerte_en_la_mezcla_pierde_la_pista(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, musica_estilo="calmado", prediccion={"id": "pagada", "modelo": "wan3"})
    _fakes_de_cierre(monkeypatch)
    monkeypatch.setattr(fp.cortes, "duracion", lambda *a: 8)
    costos = iter([.02, 0])   # se paga la pista; al recuperar sale de la caché
    monkeypatch.setattr(fp.musica, "obtener_pista", lambda *a: ({"archivo": "pista", "url": "https://r2/m.mp3"}, next(costos)))

    def muere(*a):
        raise KeyboardInterrupt   # SIGINT / reinicio con la mezcla en curso (SIGKILL u OOM: ni eso)
    monkeypatch.setattr(fp.mezcla, "mezclar_musica", muere)
    with pytest.raises(KeyboardInterrupt):
        fp._terminar_video("acme", cid, "j31", f"video:{cid}:t31", cf.cargar("acme")[cid], [], 8, "P", [], "wan3",
                           "final", "https://prov/v.mp4")
    monkeypatch.setattr(fp.mezcla, "mezclar_musica", lambda *a: {"volumenes": {}})
    fp._terminar_video("acme", cid, "j32", f"video:{cid}:t32", cf.cargar("acme")[cid], [], 8, "P", [], "wan3",
                       "final", "https://prov/v.mp4", recuperado=True)
    total = sum(g["usd"] for g in gastos.historial("acme"))
    print({g["referencia"]: g["usd"] for g in gastos.historial("acme")})
    assert total == pytest.approx(.82), "se pagaron 0,80 + 0,02 y quedó anotado menos"


def test_pnd125_interrumpir_recuperacion_registra_musica_una_vez(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path, musica_estilo="calmado",
                        prediccion={"id": "pagada", "modelo": "wan3"})
    cf.actualizar("acme", cid, prediccion={"id": "pagada", "modelo": "wan3",
                                        "referencia_gasto": f"video:{cid}:t31"})
    _fakes_de_cierre(monkeypatch)
    monkeypatch.setattr(fp.cortes, "duracion", lambda *a: 8)
    costos = iter([.02, 0, 0])
    monkeypatch.setattr(fp.musica, "obtener_pista", lambda *a: ({"archivo": "pista", "url": "https://r2/m.mp3"}, next(costos)))
    monkeypatch.setattr(fp.mezcla, "mezclar_musica", lambda *a: (_ for _ in ()).throw(KeyboardInterrupt()))
    args = ("acme", cid, "j32", f"video:{cid}:t32")
    resto = ([], 8, "P", [], "wan3", "final", "https://prov/v.mp4")
    entry = cf.cargar("acme")[cid]
    with pytest.raises(KeyboardInterrupt):
        fp._terminar_video(*args, entry, *resto, recuperado=True)
    # La fila existe antes de recuperar, aunque ya no volvamos a pagar la pista.
    assert {g["referencia"]: g["usd"] for g in gastos.historial("acme")} == {
        f"video:{cid}:t31": .8, f"video:{cid}:t32:musica": .02}
    monkeypatch.setattr(fp.mezcla, "mezclar_musica", lambda *a: {"volumenes": {}})
    monkeypatch.setattr(fp.wavespeed_common, "poll_hasta_listo", lambda *a, **k: {"outputs": ["https://prov/v.mp4"]})
    for _ in range(2):
        fp.recuperar_video({"id": 32, "payload": {"cliente": "acme", "cf_id": cid}})
    filas = gastos.historial("acme")
    assert len(filas) == 2
    assert sum(g["usd"] for g in filas) == pytest.approx(.82)


def test_pnd125_video_se_anota_apenas_descargado(base_temporal, monkeypatch, tmp_path):
    import creative_flow as cf
    import gastos
    import tareas.flowplus as fp
    cid = _sesion_video(cf, monkeypatch, tmp_path)
    _fakes_de_cierre(monkeypatch)
    def interrumpir(cliente, pieza, etapa, estado, detalle):
        if etapa == 'generacion' and estado == 'ok':
            raise KeyboardInterrupt()
    monkeypatch.setattr(fp.bitacora, 'registrar', interrumpir)
    with pytest.raises(KeyboardInterrupt):
        fp._terminar_video('acme', cid, 'j31', f'video:{cid}:t31', cf.cargar('acme')[cid], [], 8,
                           'P', [], 'wan3', 'final', 'https://prov/v.mp4')
    assert sum(g['usd'] for g in gastos.historial('acme')) == pytest.approx(.8)
