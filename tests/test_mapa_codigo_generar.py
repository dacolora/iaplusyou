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


def test_estilo_del_mapa_identico_a_head_al_regenerar():
    import re
    import subprocess
    from pathlib import Path
    raiz = Path(__file__).resolve().parents[1]
    original = subprocess.check_output(["git", "show", "HEAD:templates/mapa_codigo.html"], cwd=raiz, text=True)
    estilo = re.search(r"<style>.*?</style>", original, re.S).group()
    for fecha in ("2026-10-08", "2026-10-09"):
        _, html = mapa.documentos({"archivos": [], "rutas": [], "tablas": [], "tareas": []}, fecha)
        assert re.findall(r"<style>.*?</style>", html, re.S) == [estilo]
