import json

import pytest

JSON_OK = {"resumen": "Espejo redondo con luz cálida", "paleta": ["#F2E9E4", "#C9A227", "#1B2A41"],
           "composicion": "producto centrado", "iluminacion": "lateral cálida", "movimiento": "sin movimiento",
           "tipografia": "ninguna", "estetica": "minimalista y cálida", "storytelling": "calma en casa",
           "elementos": ["espejo", "pared", "planta"]}


def test_parsear_json_tolera_bloques_de_codigo():
    from sprints import analisis
    texto = "```json\n" + json.dumps(JSON_OK) + "\n```"
    assert analisis._parsear_json(texto)["paleta"] == ["#F2E9E4", "#C9A227", "#1B2A41"]
    assert analisis._parsear_json("Claro: " + json.dumps(JSON_OK) + " fin")["resumen"].startswith("Espejo")
    with pytest.raises(analisis.AnalisisInvalido):
        analisis._parsear_json("no hay json")
    with pytest.raises(analisis.AnalisisInvalido):
        analisis._parsear_json(json.dumps({"resumen": "solo esto"}))
    sucio = dict(JSON_OK, paleta=["#FFF", "rojo", "#000", "#111", "#222", "#333"])
    assert analisis._parsear_json(json.dumps(sucio))["paleta"] == ["#FFF", "#000", "#111", "#222", "#333"]


def test_parsear_json_descarta_hex_malformado_de_la_paleta():
    from sprints import analisis
    # Empieza por # pero no es un color: se descarta, no llega a un style="background: #zz".
    sucio = dict(JSON_OK, paleta=["#zz", "#C9A227", "#", "# fff", "#ggg", 12])
    assert analisis._parsear_json(json.dumps(sucio))["paleta"] == ["#C9A227"]


def test_analizar_imagen_manda_url_y_reintenta(monkeypatch):
    from sprints import analisis
    llamadas = []
    respuestas = ["esto no es json", json.dumps(JSON_OK)]
    def llamar_falso(content, max_tokens=700):
        llamadas.append(content)
        return respuestas.pop(0)
    monkeypatch.setattr(analisis, "_llamar", llamar_falso)
    ref = {"tipo": "imagen", "url": "https://r2/a.jpg", "intencion": ["paleta", "otro"], "intencion_otro": "textura",
           "descripcion": "me gusta la luz"}
    r = analisis.analizar(ref, marca="Vidrios Sol")
    assert r["resumen"].startswith("Espejo") and len(llamadas) == 2
    texto = llamadas[0][0]["text"]
    assert "Paleta de colores" in texto and "textura" in texto and "me gusta la luz" in texto and "Vidrios Sol" in texto
    assert llamadas[0][1] == {"type": "image", "source": {"type": "url", "url": "https://r2/a.jpg"}}
    assert "no sirvió" in llamadas[1][-1]["text"]


def test_analizar_video_usa_fotogramas_locales(monkeypatch, tmp_path):
    from sprints import analisis
    import referencias_link
    monkeypatch.setattr(referencias_link, "fotogramas", lambda ruta, n=4: [b"f1", b"f2", b"f3"][:n])
    capturado = {}
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: capturado.update(c=content) or json.dumps(JSON_OK))
    local = tmp_path / "v.mp4"; local.write_bytes(b"x")
    analisis.analizar({"tipo": "video", "url": "https://r2/v.mp4", "frame_url": "https://r2/v.frame.jpg",
                       "ruta_local": str(local), "intencion": [], "descripcion": ""})
    imagenes = [b for b in capturado["c"] if b["type"] == "image"]
    assert len(imagenes) == 3 and imagenes[0]["source"]["type"] == "base64"
    # Sin archivo local, cae al fotograma de R2.
    analisis.analizar({"tipo": "video", "url": "https://r2/v.mp4", "frame_url": "https://r2/v.frame.jpg",
                       "ruta_local": "/no/existe.mp4", "intencion": [], "descripcion": ""})
    imagenes = [b for b in capturado["c"] if b["type"] == "image"]
    assert imagenes == [{"type": "image", "source": {"type": "url", "url": "https://r2/v.frame.jpg"}}]
    with pytest.raises(analisis.AnalisisInvalido):
        analisis.analizar({"tipo": "imagen", "url": "", "intencion": [], "descripcion": ""})


def test_sugerir_personas_arma_prompt_y_colores(monkeypatch):
    from sprints import analisis, sugerencias
    import catalogo_productos, marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "Luz natural, sin saturar.")
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [{"nombre": "Espejo LED", "descripcion": "redondo"}])
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "Vidrios Sol")
    capturado = {}
    salida = {"personas": [
        {"nombre": "Cliente Premium", "resumen": "r", "descripcion": "d", "edad_rango": "35-50", "tono": "t",
         "senales_visuales": ["cocina"], "palabras_clave": ["lujo"]},
        {"nombre": "Familia joven", "resumen": "r", "descripcion": "d", "edad_rango": "28-40", "tono": "t",
         "senales_visuales": ["sala"], "palabras_clave": ["hogar"]},
        {"nombre": "sin claves"}]}
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: capturado.update(c=content) or json.dumps(salida))
    personas = sugerencias.sugerir_personas("acme", cuantas=2)
    texto = capturado["c"][0]["text"]
    assert "Vidrios Sol" in texto and "Luz natural" in texto and "Espejo LED: redondo" in texto and "Propón 2" in texto
    assert [p["nombre"] for p in personas] == ["Cliente Premium", "Familia joven"]
    assert personas[0]["color"] == sugerencias.COLORES[0] and personas[1]["color"] == sugerencias.COLORES[1]


def test_sugerir_personas_rechaza_json_malo(monkeypatch):
    from sprints import analisis, sugerencias
    import catalogo_productos, marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "")
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [])
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "X")
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: "nada")
    with pytest.raises(analisis.AnalisisInvalido):
        sugerencias.sugerir_personas("acme")


def test_sugerir_personas_coerciona_nombre_no_string(monkeypatch):
    from sprints import analisis, sugerencias
    import catalogo_productos, marca, proyectos
    monkeypatch.setattr(marca, "guia_efectiva", lambda c: "")
    monkeypatch.setattr(catalogo_productos, "listar", lambda c, cat="producto": [])
    monkeypatch.setattr(proyectos, "nombre_visible", lambda c: "X")
    capturado = {}
    salida = {"personas": [
        {"nombre": "Válido", "resumen": "r", "descripcion": "d", "edad_rango": "35-50", "tono": "t",
         "senales_visuales": ["cocina"], "palabras_clave": ["lujo"]},
        {"nombre": 123, "resumen": "r", "descripcion": "d", "edad_rango": "28-40", "tono": "t",
         "senales_visuales": ["sala"], "palabras_clave": ["hogar"]},
        {"nombre": ["x"], "resumen": "r", "descripcion": "d", "edad_rango": "20-30", "tono": "t",
         "senales_visuales": ["balcon"], "palabras_clave": ["joven"]}]}
    monkeypatch.setattr(analisis, "_llamar", lambda content, max_tokens=700: capturado.update(c=content) or json.dumps(salida))
    personas = sugerencias.sugerir_personas("acme", cuantas=3)
    assert len(personas) == 1 and personas[0]["nombre"] == "Válido" and isinstance(personas[0]["nombre"], str)
