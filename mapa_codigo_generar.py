"""Inventario estático en una salida aparte, sin importar la app.

Lee solo fuentes versionadas enumeradas por git,
extrae declaraciones con AST y no abre datos de clientes ni credenciales.
"""
import argparse
import ast
from collections import Counter
from datetime import date
from html import escape
from pathlib import Path
import subprocess

def _texto_html(texto):
    return escape(str(texto)).replace("{", "&#123;").replace("}", "&#125;")


# Bloque de estilo del mapa base: la regeneración solo reemplaza el contenido.
ESTILO_MAPA = r'''<style>
:root{
  color-scheme:dark;
  --bg:#0f1115;--panel:#1a1d24;--panel-2:#232733;--border:#2c313c;--text:#f2f3f5;--muted:#9aa3b2;--muted-2:#838b9b;
  --accent:#a78bfa;--accent-soft:#2b2352;--accent-line:#4f4390;--ok:#4fd39c;--ok-soft:#173a2c;--warn:#e8c25a;--warn-soft:#3d3416;--err:#ff7a93;--err-soft:#46202a;
  --shadow:0 4px 16px rgba(0,0,0,.35);--shadow-2:0 12px 32px rgba(0,0,0,.45);
  --display:"Space Grotesk","Helvetica Neue",Arial,sans-serif;
  --body:"Inter","Helvetica Neue",Helvetica,Arial,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:var(--body);font-size:15.5px;line-height:1.55;-webkit-font-smoothing:antialiased}
.wrap{max-width:1080px;margin:0 auto;padding-inline:16px;padding-block:0 72px}
h1,h2,h3{font-family:var(--display);text-wrap:balance;line-height:1.15;margin:0}
h1{font-size:clamp(2rem,4.2vw,2.8rem);letter-spacing:-.015em;margin-top:.35rem}
h2{font-size:1.55rem;margin-block:.15rem .5rem}
h3{font-size:1.05rem;margin-block:1.4rem .5rem}
p{margin:0 0 .8rem;max-width:70ch}
a{color:var(--accent-texto)}
code{font-family:var(--mono);font-size:.86em;background:var(--panel-2);padding:.1em .35em;border-radius:5px;overflow-wrap:anywhere}
.eyebrow{font-size:.72rem;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);font-weight:600}
header.top{padding-block:2.2rem 1rem}
header.top p.lead{font-size:1.08rem;color:var(--muted);max-width:64ch;margin-top:.8rem}
nav.nav{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--bg);border-block:1px solid var(--border);margin-inline:-16px;padding-inline:16px}
nav.nav ul{list-style:none;margin:0;padding:0;display:flex;gap:.1rem;overflow-x:auto;scrollbar-width:none}
nav.nav li a{display:block;padding:.7rem .6rem;font-size:.84rem;font-weight:500;color:var(--muted);text-decoration:none;white-space:nowrap;border-bottom:2px solid transparent}
nav.nav li a:hover,nav.nav li a:focus-visible{color:var(--text);border-color:var(--accent);outline:none}
section{padding-block:2.8rem 0}
.cristiano{font-size:1rem;color:var(--text);border-left:3px solid var(--accent);background:var(--accent-soft);padding:.6rem .9rem;border-radius:0 10px 10px 0;margin:.4rem 0 1.1rem;max-width:74ch}
.cristiano b{font-family:var(--display);color:var(--accent-texto)}
.grid{display:grid;gap:14px}
.g2{grid-template-columns:repeat(auto-fit,minmax(290px,1fr))}
.g3{grid-template-columns:repeat(auto-fit,minmax(240px,1fr))}
.card{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:18px 20px;box-shadow:var(--shadow)}
.card h3{margin-top:0}
.card .q{font-family:var(--display);font-weight:600;font-size:1rem;color:var(--muted);margin-bottom:.35rem}
.card .a{font-size:1.2rem;font-weight:700;color:var(--accent-texto);font-family:var(--display);line-height:1.25}
.card p{margin:.55rem 0 0;font-size:.93rem;color:var(--muted);max-width:none}
.card ul.lista{font-size:.93rem}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:14px}
.stat{background:var(--panel-2);border-radius:10px;padding:12px 14px}
.stat b{display:block;font-family:var(--display);font-size:1.55rem;font-variant-numeric:tabular-nums;line-height:1.1}
.stat span{font-size:.8rem;color:var(--muted)}
.chip{display:inline-block;font-size:.68rem;font-weight:600;letter-spacing:.04em;text-transform:uppercase;padding:.15em .5em;border-radius:999px;vertical-align:middle;margin-left:.3rem;white-space:nowrap}
.chip.vivo{background:var(--ok-soft);color:var(--ok)}
.chip.legado{background:var(--warn-soft);color:var(--warn)}
.chip.cli{background:var(--panel-2);color:var(--muted)}
.chip.db{background:var(--accent-soft);color:var(--accent-texto)}
/* héroe y analogía */
.hero{margin-top:1.2rem;border:1px solid var(--border);border-radius:18px;background:linear-gradient(135deg,var(--accent-soft),var(--panel) 62%);padding:24px 24px 20px;box-shadow:var(--shadow)}
.hero .una{font-family:var(--display);font-size:clamp(1.2rem,2.5vw,1.55rem);font-weight:600;line-height:1.3;max-width:36ch;text-wrap:balance;margin:0}
.hero .regla{margin:1rem 0 0;padding:.75rem 1rem;border-radius:12px;background:var(--panel);border:1px dashed var(--accent-line);font-size:.97rem;max-width:none}
.hero .regla b{color:var(--accent-texto)}
.cadena{display:flex;flex-wrap:wrap;gap:8px;align-items:stretch;margin-top:.9rem}
.cadena .nodo{flex:1 1 160px;min-width:0;background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:12px 14px}
.cadena .nodo .rol{font-family:var(--display);font-weight:700;font-size:1.02rem}
.cadena .nodo .real{font-family:var(--mono);font-size:.76rem;color:var(--accent-texto);margin-top:.2rem;word-break:break-word}
.cadena .nodo p{font-size:.86rem;color:var(--muted);margin:.45rem 0 0;max-width:none}
.cadena .flecha{align-self:center;color:var(--muted-2);font-size:1.3rem;flex:0 0 auto;padding-inline:2px}
.cadena .nodo.almacen{background:var(--accent-soft);border-color:transparent}
.cadena .nodo.cobra{background:var(--warn-soft);border-color:transparent}
@media (max-width:640px){.cadena{flex-direction:column}.cadena .flecha{transform:rotate(90deg);align-self:center;line-height:1}}
/* diagrama */
figure{margin:1rem 0 0;background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:12px}
figure .svgwrap{overflow-x:auto}
figure svg{display:block;max-width:100%;height:auto;min-width:720px;font-family:var(--body);color:var(--text)}
figcaption{font-size:.88rem;color:var(--muted);padding:10px 6px 2px}
.bx{fill:var(--panel);stroke:currentColor;stroke-width:1.1}
.band{fill:var(--panel-2);stroke:var(--border);stroke-width:1}
.band.cobra{fill:var(--warn-soft);stroke:var(--warn)}
.store{fill:var(--accent-soft);stroke:var(--accent);stroke-width:1.1}
.ln{stroke:currentColor;stroke-width:1.4;fill:none}
.ln.dash{stroke-dasharray:5 4}
.t{fill:currentColor;font-size:12.5px}
.t.b{font-weight:600;font-family:var(--display);font-size:13px}
.t.i{font-size:11.5px;fill:var(--muted);font-style:italic}
.t.s{font-size:11px;fill:var(--muted)}
.t.m{font-family:var(--mono);font-size:11.5px}
svg [data-hl]{transition:opacity .25s}
svg.paso-activo [data-hl]:not(.on){opacity:.2}
svg .on .band{stroke:var(--accent);stroke-width:2.2}
svg .on .store{stroke-width:2.2}
svg .on .ln{stroke:var(--accent);stroke-width:2.6;marker-end:url(#ar-on)}
svg .on .ln.dos{marker-start:url(#ar-on)}
svg .on .t.s,svg .on .t.i{fill:var(--text)}
/* recorrido */
.controles{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:1rem}
.btn{font:inherit;font-weight:600;font-size:.9rem;padding:.55rem 1rem;border-radius:10px;border:1px solid var(--border);background:var(--panel);color:var(--text);cursor:pointer}
.btn:hover{border-color:var(--accent)}
.btn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.btn.primario{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn[disabled]{opacity:.45;cursor:default}
.controles .donde{font-size:.86rem;color:var(--muted);font-variant-numeric:tabular-nums;margin-left:auto}
.panel-paso{margin-top:10px;padding:14px 16px;border-radius:12px;border:1px solid var(--accent-line);background:var(--panel);min-height:3.2rem}
.panel-paso b{font-family:var(--display);font-size:1.02rem}
.panel-paso .quien{display:block;font-size:.78rem;color:var(--muted);margin-top:.35rem;font-family:var(--mono);word-break:break-word}
ol.pasos{counter-reset:p;list-style:none;padding:0;margin:1rem 0 0;display:grid;gap:10px}
ol.pasos li{counter-increment:p;position:relative;padding:12px 14px 12px 58px;background:var(--panel);border:1px solid var(--border);border-radius:12px;cursor:pointer;transition:border-color .2s,box-shadow .2s}
ol.pasos li::before{content:counter(p);position:absolute;left:14px;top:12px;width:30px;height:30px;border-radius:50%;background:var(--accent);color:#fff;font-family:var(--display);font-weight:700;display:grid;place-items:center;font-size:.95rem}
ol.pasos li:hover{border-color:var(--accent)}
ol.pasos li.actual{border-color:var(--accent);box-shadow:var(--shadow-2);background:var(--accent-soft)}
ol.pasos li:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
ol.pasos li b{font-family:var(--display)}
ol.pasos li .quien{display:block;font-size:.78rem;color:var(--muted);margin-top:.3rem;font-family:var(--mono);word-break:break-word}
/* tablas */
.scroll{overflow-x:auto;margin-top:.8rem;border:1px solid var(--border);border-radius:14px;background:var(--panel)}
table.tbl{width:100%;border-collapse:collapse;font-size:.9rem}
table.tbl th{text-align:left;font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);padding:10px 12px;border-bottom:1px solid var(--border);background:var(--panel-2);white-space:nowrap}
table.tbl td{padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:top}
table.tbl tr:last-child td{border-bottom:0}
table.tbl td.f{font-family:var(--mono);font-size:.8rem;white-space:nowrap}
table.tbl td.f.w{white-space:normal;min-width:180px}
table.tbl td.n{font-variant-numeric:tabular-nums;text-align:right;color:var(--muted);white-space:nowrap}
table.tbl td.d{min-width:260px}
table.tbl td.q{font-weight:600;min-width:200px}
table.tbl td.d code,table.tbl td.p code{white-space:nowrap}
table.tbl tr.grp td{background:var(--panel-2);font-family:var(--display);font-weight:600;font-size:.95rem;padding-block:10px}
table.tbl tr.grp td small{font-family:var(--body);font-weight:400;color:var(--muted);font-size:.8rem;margin-left:.5rem}
.buscar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:1rem}
.buscar input{flex:1 1 260px;font:inherit;padding:.65rem .95rem;border:1px solid var(--border);border-radius:10px;background:var(--panel);color:var(--text)}
.buscar input:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.buscar output{font-size:.86rem;color:var(--muted);font-variant-numeric:tabular-nums}
.filtros{display:flex;flex-wrap:wrap;gap:6px;margin-top:.7rem}
.filtros button{font:inherit;font-size:.8rem;font-weight:600;padding:.35rem .75rem;border-radius:999px;border:1px solid var(--border);background:var(--panel);color:var(--muted);cursor:pointer}
.filtros button:hover{border-color:var(--accent);color:var(--text)}
.filtros button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
.filtros button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
ul.lista{padding-left:1.2rem;margin:.4rem 0 0}
ul.lista li{margin-bottom:.45rem}
.faq details{border:1px solid var(--border);border-radius:12px;background:var(--panel);padding:0 16px;margin-top:8px}
.faq summary{cursor:pointer;font-family:var(--display);font-weight:600;padding:13px 0;list-style:none;display:flex;gap:10px;align-items:baseline}
.faq summary::-webkit-details-marker{display:none}
.faq summary::before{content:"+";color:var(--accent-texto);font-weight:700;width:1em;flex:0 0 auto}
.faq details[open] summary::before{content:"–"}
.faq details p{padding-bottom:13px;color:var(--muted);max-width:none;margin:0}
dl.glos{display:grid;grid-template-columns:max-content 1fr;gap:.45rem 1rem;margin:1rem 0 0;font-size:.93rem}
dl.glos dt{font-family:var(--mono);font-size:.82rem;color:var(--accent-texto);padding-top:.15rem}
dl.glos dd{margin:0;max-width:70ch}
.aviso{border-left:3px solid var(--warn);background:var(--warn-soft);padding:12px 16px;border-radius:0 12px 12px 0;margin-top:1rem}
.aviso p{margin:0 0 .45rem;max-width:none}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--border);font-size:.82rem;color:var(--muted)}
@media (max-width:640px){dl.glos{grid-template-columns:1fr}dl.glos dd{margin-bottom:.5rem}ol.pasos li{padding-left:52px}.hero{padding:18px 16px}}
@media (prefers-reduced-motion:no-preference){html{scroll-behavior:smooth}}
@media (prefers-reduced-motion:reduce){svg [data-hl],ol.pasos li{transition:none}}
[hidden]{display:none!important}
.barra-app{display:flex;gap:12px;align-items:center;flex-wrap:wrap;padding:10px 16px;background:var(--panel);border-bottom:1px solid var(--border);font-size:.86rem;color:var(--muted)}
.barra-app a{font-weight:600;text-decoration:none}
.barra-app .solo{margin-left:auto}
</style>'''

DIRECTORIOS = frozenset({"auth", "conectores", "deploy", "doctrina", "editor", "final_edition", "guiones",
    "nicho", "providers", "referentes", "rendimiento", "sprints", "static", "storage", "tareas", "templates",
    "tests", "uploaders", "migrations"})
EXTENSIONES = frozenset({".py", ".html", ".js", ".css"})
GENERADOS = frozenset({"templates/mapa_codigo.html", "static/style.css"})


def inventariar(raiz, nombres):
    """Devuelve hechos del código; no ejecuta módulos ni lee estado local."""
    raiz = Path(raiz)
    archivos, rutas, tablas, tareas = [], [], [], []
    for nombre in sorted(set(nombres)):
        ruta = Path(nombre)
        if (ruta.is_absolute() or ".." in ruta.parts or ruta.suffix not in EXTENSIONES or nombre in GENERADOS
                or (len(ruta.parts) > 1 and ruta.parts[0] not in DIRECTORIOS)):
            continue
        local = raiz / ruta
        if not local.is_file() or local.is_symlink():
            continue
        texto = local.read_text(encoding="utf-8")
        fila = {"archivo": nombre, "lineas": len(texto.splitlines()), "area": ruta.parts[0] if len(ruta.parts) > 1 else "raíz",
                "imports": [], "funciones": [], "descripcion": ""}
        if ruta.suffix == ".py":
            arbol = ast.parse(texto, filename=nombre)
            fila["descripcion"] = (ast.get_docstring(arbol) or "").split("\n", 1)[0][:220]
            paquete = ".".join(ruta.parts[:-1])
            for nodo in ast.walk(arbol):
                if isinstance(nodo, ast.Import):
                    fila["imports"].extend(n.name for n in nodo.names)
                elif isinstance(nodo, ast.ImportFrom):
                    base = nodo.module or ""
                    if nodo.level:
                        partes = paquete.split(".") if paquete else []
                        base = ".".join(partes[:len(partes) - nodo.level + 1] + ([base] if base else []))
                    fila["imports"].extend((base + "." + n.name).strip(".") for n in nodo.names)
                elif isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fila["funciones"].append({"nombre": nodo.name, "linea": nodo.lineno})
                    for dec in nodo.decorator_list:
                        if not isinstance(dec, ast.Call) or not dec.args or not isinstance(dec.args[0], ast.Constant):
                            continue
                        valor = dec.args[0].value
                        if not isinstance(valor, str):
                            continue
                        if isinstance(dec.func, ast.Attribute) and dec.func.attr in {"route", "get", "post", "put", "delete", "patch"}:
                            metodos = dec.func.attr.upper()
                            if dec.func.attr == "route":
                                metodos = "GET"
                                for kw in dec.keywords:
                                    if kw.arg == "methods":
                                        metodos = ",".join(ast.literal_eval(kw.value))
                            rutas.append({"archivo": nombre, "linea": dec.lineno, "funcion": nodo.name, "ruta": valor, "metodo": metodos})
                        elif isinstance(dec.func, ast.Name) and dec.func.id == "registrar" and ruta.parts[0] == "tareas":
                            tareas.append({"archivo": nombre, "linea": dec.lineno, "nombre": valor, "funcion": nodo.name})
                elif isinstance(nodo, ast.Call):
                    fun = nodo.func.id if isinstance(nodo.func, ast.Name) else nodo.func.attr if isinstance(nodo.func, ast.Attribute) else ""
                    if nombre == "db.py" and fun == "Table" and nodo.args and isinstance(nodo.args[0], ast.Constant):
                        tablas.append({"archivo": nombre, "linea": nodo.lineno, "nombre": nodo.args[0].value})
            fila["imports"] = sorted(set(fila["imports"]))
        archivos.append(fila)
    return {"archivos": archivos, "rutas": rutas, "tablas": tablas, "tareas": tareas}


def _tabla_md(filas):
    return "\n".join("| " + " | ".join(str(v).replace("|", "\\|").replace("\n", " ") for v in fila) + " |" for fila in filas)


def _tabla_html(filas):
    return "\n".join("<tr>" + "".join("<td>" + _texto_html(str(v)) + "</td>" for v in fila) + "</tr>" for fila in filas)


def documentos(inv, fecha):
    """Dos representaciones del mismo inventario, con alcance explícito."""
    archivos = inv["archivos"]
    counts = Counter(Path(f["archivo"]).suffix for f in archivos)
    resumen = (f"{len(archivos)} fuentes: {counts['.py']} Python, {counts['.html']} plantillas, "
               f"{counts['.js']} JavaScript y {counts['.css']} CSS. {len(inv['tablas'])} declaraciones Table en db.py; "
               f"{len(inv['rutas'])} decoradores de rutas; {len(inv['tareas'])} tareas con @registrar en tareas/.")
    alcance = ("Inventario del código local versionado. Los conteos son declaraciones estáticas: "
               "las rutas de blueprints se muestran relativas a su prefijo y las altas por add_url_rule no se cuentan como decoradores. "
               "Las descripciones proceden del docstring del módulo; las líneas, del archivo actual. "
               "Se excluyen datos de clientes, secretos, submódulos y los dos artefactos generados mapa_codigo.html/style.css.")
    entradas = []
    for f in archivos:
        detalle = f["descripcion"] or ", ".join(x["nombre"] for x in f["funciones"][:6]) or "Fuente de " + f["area"]
        entradas.append((f["archivo"], f["lineas"], f["area"], detalle))
    secciones = [
        ("Inventario", ("Archivo", "Líneas", "Área", "Docstring o funciones declaradas"), entradas),
        ("Rutas declaradas", ("Método", "Ruta relativa", "Función", "Dónde"),
            [(r["metodo"], r["ruta"], r["funcion"], f"{r['archivo']}:{r['linea']}") for r in inv["rutas"]]),
        ("Tablas declaradas", ("Tabla", "Dónde"), [(t["nombre"], f"{t['archivo']}:{t['linea']}") for t in inv["tablas"]]),
        ("Tareas declaradas", ("Tipo", "Función", "Dónde"), [(t["nombre"], t["funcion"], f"{t['archivo']}:{t['linea']}") for t in inv["tareas"]]),
    ]
    md = ["# Mapa del repositorio", f"\nRegenerado desde el código del worktree el {fecha}.", resumen, alcance,
          "\nLa guía del agente es AGENTS.md; las reglas de cada área viven en .claude/skills/. "
          "dashboard.py declara la web; worker.py ejecuta las tareas registradas. trabajos.py contiene tanto encolado como hilos: "
          "el inventario no presume que toda llamada pagada pase por el worker."]
    for titulo, cabecera, filas in secciones:
        md.extend(["\n## " + titulo, _tabla_md([cabecera, ["---"] * len(cabecera)] + filas)])
    md.extend(["\n## Cómo regenerarlo", "`python3 mapa_codigo_generar.py --salida /tmp/inventario` lee las fuentes versionadas con AST. "
        "La publicación del artifact del mapa corresponde a Claude."])
    html = ['''{# Documentación interna en español; barra traducida por catálogo. Generado por mapa_codigo_generar.py. #}
<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mapa de Creatv Machine</title><link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
{% raw %}''' + ESTILO_MAPA + '''{% endraw %}</head><body>
<div id="mapa-barra"><a href="{{ url_for('panel') }}">{{ _('Volver al panel') }}</a> · <span>{{ _('Mapa del código') }}</span> · <span>{{ _('Solo lo ve el administrador') }}</span>
{% if idioma_ui != 'es' %}<span>{{ _('Este mapa es documentación interna y está en español.') }}</span>{% endif %}</div>
{% raw %}''', '<main class="panel-contenido"><h1>Mapa de Creatv Machine</h1>',
        '<p>Regenerado desde el código del worktree el ' + _texto_html(fecha) + '.</p>', '<p>' + _texto_html(resumen) + '</p>', '<p>' + _texto_html(alcance) + '</p>',
        '''<svg id="svg-mapa" role="img" aria-label="Entradas del código" viewBox="0 0 700 100" width="100%" height="100">
<rect x="5" y="5" width="330" height="90" fill="none" stroke="currentColor"/><text x="25" y="40" fill="currentColor">Web: dashboard.py</text><text x="25" y="65" fill="currentColor">Cola e hilos: trabajos.py</text>
<rect x="365" y="5" width="330" height="90" fill="none" stroke="currentColor"/><text x="385" y="40" fill="currentColor">Worker: worker.py</text><text x="385" y="65" fill="currentColor">Registro: tareas/__init__.py</text></svg>
<label for="buscar">Filtrar inventario</label><input id="buscar" type="search" placeholder="Archivo, área o función">''']
    for num, (titulo, cabecera, filas) in enumerate(secciones):
        html.extend(['<section><h2>' + _texto_html(titulo) + '</h2><div class="tabla-scroll"><table' + (' id="inv"' if num == 0 else '') + '><thead><tr>',
            ''.join('<th>' + _texto_html(c) + '</th>' for c in cabecera), '</tr></thead><tbody>', _tabla_html(filas), '</tbody></table></div></section>'])
    html.extend(['''<section><h2>Antes de exponerlo</h2><p>Las reglas de autorización, gasto y publicación se consultan en AGENTS.md y las skills. Este mapa describe declaraciones del código; la publicación del artifact corresponde a Claude.</p></section>
<script>
document.getElementById('buscar').addEventListener('input', function () {
  var q = this.value.toLowerCase();
  document.querySelectorAll('#inv tbody tr').forEach(function (fila) { fila.hidden = fila.textContent.toLowerCase().indexOf(q) < 0; });
});
</script></main>{% endraw %}</body></html>'''])
    return "\n\n".join(md) + "\n", "\n".join(html) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fecha", default=date.today().isoformat())
    parser.add_argument("--salida", required=True, type=Path, help="Carpeta aparte para el inventario")
    args = parser.parse_args()
    raiz = Path(__file__).resolve().parent
    salida = args.salida.resolve()
    destinos = (salida / "ESTRUCTURA.md", salida / "mapa_codigo.html")
    protegidos = {raiz / "ESTRUCTURA.md", raiz / "templates/mapa_codigo.html"}
    if any(p in protegidos for p in destinos):
        parser.error("La salida debe estar aparte del mapa del producto")
    listado = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=raiz)
    inv = inventariar(raiz, [s.decode() for s in listado.split(b"\0") if s])
    md, html = documentos(inv, args.fecha)
    salida.mkdir(parents=True, exist_ok=True)
    destinos[0].write_text(md, encoding="utf-8")
    destinos[1].write_text(html, encoding="utf-8")
    print(f"Inventario en {salida}: {len(inv['archivos'])} fuentes.")


if __name__ == "__main__":
    main()
