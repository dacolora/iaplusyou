from datetime import datetime

import pytest


def test_limpiar_y_hash():
    from nicho.fuentes import base
    assert base.limpiar_texto("  Hola\x00 \n\n mundo\t ya  ") == "Hola mundo ya"
    assert len(base.limpiar_texto("x" * 5000)) == base.MAX_TEXTO
    assert base.hash_texto("Hola   Mundo") == base.hash_texto("hola mundo") and len(base.hash_texto("a")) == 16


def test_normalizar_comentario():
    from nicho.fuentes import base
    c = base.normalizar_comentario({"texto": " La garrafa <b>pesa</b> ", "url": "https://r.com/x", "contexto": "Post: garrafas",
                                    "puntuacion": "12", "fecha": "2026-03-04T10:20:30Z", "extra": {"sub": "sweden"}})
    assert tuple(c) == base.CLAVES_COMENTARIO
    assert c["texto"] == "La garrafa <b>pesa</b>" and c["fuente_id"] == base.hash_texto("La garrafa <b>pesa</b>")
    assert c["url"] == "https://r.com/x" and c["puntuacion"] == 12 and c["fecha"] == "2026-03-04T10:20:30" and c["extra"] == {"sub": "sweden"}
    assert base.normalizar_comentario({"texto": "ab"}) is None
    assert base.normalizar_comentario({"texto": None}) is None
    c2 = base.normalizar_comentario({"fuente_id": " t1_abc ", "texto": "vale", "url": "javascript:x", "puntuacion": "muchos",
                                     "fecha": 1700000000, "extra": "no dict"})
    assert c2["fuente_id"] == "t1_abc" and c2["url"] is None and c2["puntuacion"] is None and c2["extra"] == {}
    assert c2["fecha"] == datetime.fromtimestamp(1700000000).strftime("%Y-%m-%dT%H:%M:%S")
    assert base.normalizar_comentario({"texto": "vale", "fecha": "2026-01-02"})["fecha"] == "2026-01-02T00:00:00"
    assert base.normalizar_comentario({"texto": "vale", "fecha": "ayer"})["fecha"] is None
    assert base.normalizar_comentario({"texto": "vale", "puntuacion": True})["puntuacion"] is None


def test_error_fuente_y_fuente_base():
    from nicho.fuentes import base
    e = base.ErrorFuente("Reddit no aceptó las llaves.")
    assert e.usuario == str(e) == "Reddit no aceptó las llaves."
    f = base.Fuente()
    assert f.probar()["ok"] is True and f.estimar({}) is None
    with pytest.raises(NotImplementedError):
        list(f.recolectar({}))


def test_registro_por_tipo():
    from nicho import fuentes
    assert fuentes.tipos() == ("texto", "csv")
    assert fuentes.por_tipo("texto").tipo == "texto" and fuentes.por_tipo("csv").tipo == "csv"
    with pytest.raises(KeyError):
        fuentes.por_tipo("magia")
    assert fuentes.NOMBRES["apify"].startswith("Amazon")


def test_partir_texto_modos():
    from nicho.fuentes import texto
    pegado = "Primer comentario\n\nSegundo, que sigue\nen dos líneas\n\n\n  \nTercero"
    assert texto.partir_texto(pegado, "lineas") == ["Primer comentario", "Segundo, que sigue", "en dos líneas", "Tercero"]
    assert texto.partir_texto(pegado, "parrafos") == ["Primer comentario", "Segundo, que sigue en dos líneas", "Tercero"]
    assert texto.partir_texto("", "lineas") == [] and texto.partir_texto(None, "parrafos") == []
    assert texto.partir_texto("a\nb", "modo raro") == ["a", "b"]         # modo desconocido -> lineas


def test_fuente_texto_recolecta_normalizado():
    from nicho import fuentes
    lista = list(fuentes.por_tipo("texto")().recolectar({"texto": "Muy pesada la garrafa\nok\n\nGotea en el estante", "modo": "lineas"}))
    assert [c["texto"] for c in lista] == ["Muy pesada la garrafa", "Gotea en el estante"]     # "ok" no llega a MIN_TEXTO
    assert lista[0]["fuente_id"] and lista[0]["url"] is None and lista[0]["extra"] == {}


def _xlsx(filas):
    import io
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    for f in filas:
        ws.append(f)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_leer_csv_detecta_columnas():
    from nicho.fuentes import archivo
    csv = "Review;Rating;Date;Link\nLa garrafa pesa y gotea;4;2026-01-02;https://a.com/1\nab;5;;\nSe pega la tapa;;;\n"
    lista = archivo.leer_archivo("resenas.csv", csv.encode("utf-8"))
    assert [c["texto"] for c in lista] == ["La garrafa pesa y gotea", "Se pega la tapa"]
    assert lista[0]["puntuacion"] == 4 and lista[0]["fecha"] == "2026-01-02T00:00:00" and lista[0]["url"] == "https://a.com/1"
    assert lista[1]["puntuacion"] is None and lista[1]["url"] is None


def test_leer_csv_sin_encabezado_conocido_usa_columna_mas_larga():
    from nicho.fuentes import archivo
    csv = "id,cosa,otra\n1,Un comentario bastante largo sobre la garrafa que pesa,x\n2,Otro comentario igual de largo sobre la tapa pegajosa,y\n"
    assert [c["texto"] for c in archivo.leer_archivo("x.csv", csv.encode())] == [
        "Un comentario bastante largo sobre la garrafa que pesa", "Otro comentario igual de largo sobre la tapa pegajosa"]


def test_leer_xlsx():
    from nicho.fuentes import archivo
    contenido = _xlsx([["texto", "likes"], ["Muy pesada, no la vuelvo a comprar", 12], [None, 3], ["Gotea en el estante", "7"]])
    lista = archivo.leer_archivo("r.xlsx", contenido)
    assert [(c["texto"], c["puntuacion"]) for c in lista] == [("Muy pesada, no la vuelvo a comprar", 12), ("Gotea en el estante", 7)]


def test_leer_xlsx_corta_apenas_pasa_max_filas_sin_cargar_todo():
    """I2: con más de MAX_FILAS filas, _filas_xlsx debe cortar apenas se pasa
    (no materializar la hoja completa antes de recién ahí quejarse)."""
    from nicho.fuentes import archivo, base
    filas = [["texto"]] + [[f"comentario {i} bien corto"] for i in range(archivo.MAX_FILAS + 2)]
    contenido = _xlsx(filas)
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("grande.xlsx", contenido)


def test_leer_archivo_errores():
    from nicho.fuentes import archivo, base
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.txt", b"hola")
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.csv", b"a" * (archivo.MAX_BYTES + 1))
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.csv", b"")
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.csv", b"a,b\n1,2\n3,4\n")            # sin columna de texto
    muchas = "texto\n" + "\n".join(f"comentario {i} largo de verdad" for i in range(archivo.MAX_FILAS + 1))
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.csv", muchas.encode())
    with pytest.raises(base.ErrorFuente):
        archivo.leer_archivo("x.xlsx", b"no es un excel")


def test_fuente_archivo_recolecta():
    from nicho import fuentes
    lista = list(fuentes.por_tipo("csv")().recolectar({"nombre": "r.csv", "contenido": b"comentario\nLa tapa se pega siempre\n"}))
    assert lista[0]["texto"] == "La tapa se pega siempre"
