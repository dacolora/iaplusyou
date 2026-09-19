import os
import time

import pytest

import materiales as m


@pytest.fixture()
def r2_falso(monkeypatch):
    subidos = []
    borrados = []
    from storage import r2_uploader
    monkeypatch.setattr(r2_uploader, "upload_file", lambda p, k, ct: (subidos.append((p, k, ct)), f"https://r2/{k}")[1])
    monkeypatch.setattr(r2_uploader, "delete_file", lambda k: borrados.append(k))
    return {"subidos": subidos, "borrados": borrados}


def test_hash_clave_es_estable_y_distingue_partes():
    assert m.hash_clave("hola", "voz1", "es") == m.hash_clave("hola", "voz1", "es")
    assert m.hash_clave("hola", "voz1", "es") != m.hash_clave("hola", "voz1", "en")
    assert m.hash_clave("a", "bc") != m.hash_clave("ab", "c")


def test_obtener_o_crear_solo_produce_una_vez(base_temporal, r2_falso):
    llamadas = []

    def producir():
        llamadas.append(1)
        return {"tipo": "audio", "origen": "voz", "url": "https://r2/v.mp3", "bytes": 100, "costo_usd": 0.004}
    h = m.hash_clave("texto", "voz", "es")
    mat1, creado1 = m.obtener_o_crear("acme", h, producir)
    mat2, creado2 = m.obtener_o_crear("acme", h, producir)
    assert creado1 and not creado2
    assert mat1["id"] == mat2["id"] and llamadas == [1]


def test_subir_deduplica_por_contenido(base_temporal, r2_falso, tmp_path):
    f = tmp_path / "a.png"
    f.write_bytes(b"\x89PNG-contenido")
    a = m.subir("acme", str(f), "clientes/acme/materiales/a.png", "image/png", tipo="imagen", origen="subida")
    b = m.subir("acme", str(f), "clientes/acme/materiales/b.png", "image/png", tipo="imagen", origen="subida")
    assert a["id"] == b["id"]
    assert len(r2_falso["subidos"]) == 1


def test_materiales_de_otro_cliente_no_se_mezclan(base_temporal, r2_falso):
    prod = lambda: {"tipo": "audio", "origen": "voz", "url": "u", "bytes": 1}
    h = m.hash_clave("x")
    a, _ = m.obtener_o_crear("acme", h, prod)
    b, _ = m.obtener_o_crear("otro", h, prod)
    assert a["id"] != b["id"]


def test_validar_subida_por_tipo_tamano_y_duracion():
    m.validar_subida("imagen", 1000)
    with pytest.raises(m.SubidaInvalida, match="20 MB"):
        m.validar_subida("imagen", 21 * 1024 * 1024)
    with pytest.raises(m.SubidaInvalida, match="2 min"):
        m.validar_subida("video", 1000, duracion_ms=121000)
    with pytest.raises(m.SubidaInvalida, match="tipo"):
        m.validar_subida("pdf", 10)


def test_borrar_falla_si_esta_en_uso(base_temporal, r2_falso):
    import db
    mat = m.registrar("acme", tipo="imagen", origen="subida", url="https://r2/clientes/acme/x.png", hash="h1", bytes=5)
    with db.conectar() as con:
        con.execute(db.edicion.insert().values(
            cliente="acme", creado_en=db.ahora(), actualizado_en=db.ahora(), tipo="video", nombre="e",
            documento={"materiales": [mat["id"]]}, version_n=0, estado="borrador"))
    assert m.en_uso("acme", mat["id"])
    with pytest.raises(m.MaterialEnUso):
        m.borrar("acme", mat["id"])


def test_borrar_libre_quita_de_r2_y_de_la_base(base_temporal, r2_falso):
    mat = m.registrar("acme", tipo="imagen", origen="subida", url="https://r2/clientes/acme/x.png", hash="h2", bytes=5)
    m.borrar("acme", mat["id"])
    assert m.buscar_hash("acme", "h2") is None
    assert r2_falso["borrados"] == ["clientes/acme/x.png"]


def test_limpiar_sin_uso_solo_efimeros_viejos(base_temporal, r2_falso, monkeypatch):
    import db
    viejo = "2020-01-01T00:00:00"
    a = m.registrar("acme", tipo="png_texto", origen="texto", url="https://r2/clientes/acme/t.png", hash="p1", bytes=1)
    b = m.registrar("acme", tipo="video", origen="subida", url="https://r2/clientes/acme/v.mp4", hash="v1", bytes=1)
    with db.conectar() as con:
        con.execute(db.material.update().values(usado_en=viejo, creado_en=viejo))
    assert m.limpiar_sin_uso(dias=30) == 1
    assert m.buscar_hash("acme", "p1") is None
    assert m.buscar_hash("acme", "v1") is not None


def test_bytes_usados_suma_por_cliente(base_temporal, r2_falso):
    m.registrar("acme", tipo="video", origen="subida", url="u1", hash="x1", bytes=70)
    m.registrar("acme", tipo="audio", origen="subida", url="u2", hash="x2", bytes=30)
    m.registrar("otro", tipo="audio", origen="subida", url="u3", hash="x3", bytes=999)
    assert m.bytes_usados("acme") == 100
