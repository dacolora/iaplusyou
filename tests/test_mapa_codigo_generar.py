"""El generador inspecciona código de ejemplo; estas pruebas no leen documentos."""
import mapa_codigo_generar as mapa


def test_pnd100_inventario_estatico_con_lineas_y_cambios(tmp_path):
    (tmp_path / "dashboard.py").write_text('"""Web de ejemplo."""\nimport trabajos\n@app.get("/hoy")\ndef hoy(): pass\n')
    (tmp_path / "db.py").write_text('import sqlalchemy as sa\nproducto = sa.Table("producto", metadata)\n')
    (tmp_path / "tareas").mkdir()
    (tmp_path / "tareas" / "ejemplo.py").write_text('@registrar("ejemplo")\ndef ejecutar(tarea): pass\n')
    (tmp_path / "clientes").mkdir()
    (tmp_path / "clientes" / "secreto.py").write_text('esto no debe analizarse')
    nombres = ["dashboard.py", "db.py", "tareas/ejemplo.py", "clientes/secreto.py", "usuarios.json", "templates/mapa_codigo.html"]
    inv = mapa.inventariar(tmp_path, nombres)
    assert [f["archivo"] for f in inv["archivos"]] == ["dashboard.py", "db.py", "tareas/ejemplo.py"]
    assert inv["rutas"] == [{"archivo": "dashboard.py", "linea": 3, "funcion": "hoy", "ruta": "/hoy", "metodo": "GET"}]
    assert inv["tablas"] == [{"archivo": "db.py", "linea": 2, "nombre": "producto"}]
    assert inv["tareas"] == [{"archivo": "tareas/ejemplo.py", "linea": 1, "nombre": "ejemplo", "funcion": "ejecutar"}]
    assert inv["archivos"][0]["imports"] == ["trabajos"]
    (tmp_path / "dashboard.py").write_text('import gastos\n@app.post("/nuevo")\ndef nuevo(): pass\n')
    inv2 = mapa.inventariar(tmp_path, nombres)
    assert inv2["rutas"][0]["ruta"] == "/nuevo" and inv2["rutas"][0]["metodo"] == "POST"
    assert inv2["archivos"][0]["imports"] == ["gastos"]


def test_pnd100_imports_relativos_aliases_y_no_ejecuta_fuentes(tmp_path):
    (tmp_path / "tareas").mkdir()
    (tmp_path / "tareas" / "a.py").write_text('from . import b\nraise RuntimeError("no importar")\n@registrar("a")\n@otra\ndef ejecutar(t): pass\n')
    inv = mapa.inventariar(tmp_path, ["tareas/a.py"])
    assert inv["archivos"][0]["imports"] == ["tareas.b"]
    assert inv["tareas"][0]["linea"] == 3


def test_estilo_del_mapa_identico_al_disco_al_regenerar():
    import re
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    original = (raiz / "templates/mapa_codigo.html").read_text()
    estilo = re.search(r"<style>.*?</style>", original, re.S).group()
    for fecha in ("2026-10-08", "2026-10-09"):
        _, html = mapa.documentos({"archivos": [], "rutas": [], "tablas": [], "tareas": []}, fecha)
        assert re.findall(r"<style>.*?</style>", html, re.S) == [estilo]


def test_salida_aparte_solo_versionados_sin_pisar_mapa(tmp_path, monkeypatch):
    raiz = tmp_path / 'repo'; raiz.mkdir()
    (raiz / 'templates').mkdir()
    (raiz / 'dashboard.py').write_text('def vista(): pass')
    (raiz / 'sin_versionar.py').write_text('raise RuntimeError("no inventariar")')
    estructura = raiz / 'ESTRUCTURA.md'; estructura.write_text('Mapa en llano')
    plantilla = raiz / 'templates/mapa_codigo.html'; plantilla.write_text('<p>Mapa en llano</p>')
    def listado(args, **kwargs):
        return b'dashboard.py\0' + (b'sin_versionar.py\0' if '--others' in args else b'')
    monkeypatch.setattr(mapa.subprocess, 'check_output', listado)
    monkeypatch.setattr(mapa, '__file__', str(raiz / 'mapa_codigo_generar.py'))
    salida = tmp_path / 'inventario'
    monkeypatch.setattr('sys.argv', ['mapa', '--salida', str(salida), '--fecha', '2026-10-08'])
    mapa.main()
    assert estructura.read_text() == 'Mapa en llano'
    assert plantilla.read_text() == '<p>Mapa en llano</p>'
    assert (salida / 'ESTRUCTURA.md').exists() and (salida / 'mapa_codigo.html').exists()
    assert 'sin_versionar.py' not in (salida / 'mapa_codigo.html').read_text()


def test_texto_del_inventario_no_puede_salir_de_raw(tmp_path):
    from jinja2 import Environment
    ataque = '{% endraw %}INJECT={{ 7 * 7 }}{% raw %}'
    nombre = 'archivo' + ataque + '.py'
    (tmp_path / nombre).write_text('"""' + ataque + '"""\ndef vista(): pass')
    inv = mapa.inventariar(tmp_path, [nombre])
    _, html = mapa.documentos(inv, ataque)
    seguro = ataque.replace('{', '&#123;').replace('}', '&#125;')
    assert seguro in html
    render = Environment().from_string(html).render(url_for=lambda *a, **k: '/panel', _=lambda s:s, idioma_ui='es')
    assert 'INJECT=49' not in render
    assert render.count(seguro) >= 2
