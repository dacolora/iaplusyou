"""PostToolUse (Edit | Write | MultiEdit): revisa el archivo recién tocado.

Bloquea (sale con 2 y Claude ve el motivo) solo lo que de verdad rompe:
  .py         no compila
  .html       Jinja no la puede leer, una macro abre más <div> de los que cierra,
              o la plantilla quedó con un balance de <div> distinto al de HEAD
              (2026-09-28: las macros de tarjeta salieron sin su </div> y Crear se
              vio «en escalera» en producción; ningún test de texto lo vio)
  .js/.mjs    `node --check` falla
  .po         quedan entradas `fuzzy` (no se usan en tiempo de ejecución)
  cualquiera  marcas de conflicto de un merge
Lo que falta para revisar (sin venv, sin node) se dice con todas las letras y
no bloquea: un archivo sin revisar no se presenta como revisado.

Corre con el python3 del sistema; Jinja y Babel se revisan con el python del
venv del proyecto (el del worktree o, si no tiene, el del checkout principal).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

PROBAR_PLANTILLA = r"""
import json, re, sys
import jinja2
ruta = sys.argv[1]
src = open(ruta, encoding="utf-8").read()
base = open(sys.argv[2], encoding="utf-8").read() if sys.argv[2] != "-" else "-"
problemas = []
try:
    jinja2.Environment(extensions=["jinja2.ext.i18n", "jinja2.ext.do", "jinja2.ext.loopcontrols"]).parse(src)
except jinja2.TemplateSyntaxError as e:
    problemas.append("Jinja no la puede leer (línea %s): %s" % (e.lineno, e.message))
macro = re.compile(r"{%-?\s*macro\s+(\w+).*?%}(.*?){%-?\s*endmacro\s*-?%}", re.S)
def balance(texto):
    return len(re.findall(r"<div\b", texto)) - len(re.findall(r"</div\s*>", texto))
for m in macro.finditer(src):
    b = balance(m.group(2))
    if b:
        problemas.append("la macro %s abre %d <div> de más" % (m.group(1), b) if b > 0
                         else "la macro %s cierra %d <div> de más" % (m.group(1), -b))
ahora = balance(src)
antes = balance(base) if base != "-" else 0
if ahora != antes:
    problemas.append("la plantilla quedó con %+d <div> sin pareja respecto de %s"
                     % (ahora - antes, "HEAD" if base != "-" else "cero (archivo nuevo)"))
print(json.dumps(problemas))
"""

PROBAR_PO = r"""
import json, sys
from babel.messages.pofile import read_po
with open(sys.argv[1], "rb") as f:
    cat = read_po(f)
fuzzy = [m.id if isinstance(m.id, str) else m.id[0] for m in cat if m.id and m.fuzzy]
print(json.dumps(fuzzy))
"""


def correr(args, **kw):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=60, **kw)
    except Exception as e:  # pragma: no cover - entorno roto
        return subprocess.CompletedProcess(args, 99, "", str(e))


def raiz_de(ruta):
    r = correr(["git", "-C", os.path.dirname(ruta) or ".", "rev-parse", "--show-toplevel"])
    return r.stdout.strip() if r.returncode == 0 else None


def python_del_venv(raiz):
    candidatos = [os.path.join(raiz, "venv", "bin", "python3")]
    r = correr(["git", "-C", raiz, "rev-parse", "--path-format=absolute", "--git-common-dir"])
    if r.returncode == 0:
        candidatos.append(os.path.join(os.path.dirname(r.stdout.strip()), "venv", "bin", "python3"))
    for c in candidatos:
        if os.access(c, os.X_OK):
            return c
    return None


def version_en_head(raiz, rel):
    r = correr(["git", "-C", raiz, "show", "HEAD:" + rel])
    return r.stdout if r.returncode == 0 else None


def marcas_de_conflicto(texto):
    return [i + 1 for i, l in enumerate(texto.split("\n")) if re.match(r"^(<{7}|>{7})( |$)", l)]


def revisar(ruta):
    """(errores, avisos) del archivo."""
    errores, avisos = [], []
    raiz = raiz_de(ruta)
    if not raiz or not os.path.isfile(os.path.join(raiz, "dashboard.py")):
        return errores, avisos  # no es iaplusyou
    rel = os.path.relpath(ruta, raiz)
    try:
        texto = open(ruta, encoding="utf-8").read()
    except (UnicodeDecodeError, OSError):
        return errores, avisos  # binario o ilegible: nada que revisar
    lineas = marcas_de_conflicto(texto)
    if lineas:
        errores.append("marcas de conflicto de un merge en las líneas %s" % ", ".join(map(str, lineas[:10])))
    py = python_del_venv(raiz)

    if ruta.endswith(".py"):
        interprete = py or sys.executable
        r = correr([interprete, "-c",
                    "import sys; compile(open(sys.argv[1], encoding='utf-8').read(), sys.argv[1], 'exec')", ruta])
        if r.returncode != 0:
            errores.append("no compila:\n" + "\n".join(r.stderr.strip().splitlines()[-5:]))
    elif ruta.endswith(".html") and rel.startswith("templates" + os.sep):
        if not py:
            avisos.append("no se revisó la plantilla: no hay venv con Jinja (ni en el worktree ni en el checkout principal)")
        else:
            base = version_en_head(raiz, rel)
            ruta_base = "-"
            if base is not None:
                with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
                    f.write(base)
                    ruta_base = f.name
            try:
                r = correr([py, "-c", PROBAR_PLANTILLA, ruta, ruta_base])
            finally:
                if ruta_base != "-":
                    os.unlink(ruta_base)
            if r.returncode != 0:
                avisos.append("no se pudo revisar la plantilla: " + r.stderr.strip()[-300:])
            else:
                errores.extend(json.loads(r.stdout or "[]"))
    elif ruta.endswith((".js", ".mjs")):
        node = shutil.which("node")
        if not node:
            avisos.append("no se revisó el JS: `node` no está instalado")
        else:
            objetivo = ruta
            temporal = None
            # `node --check` da por buena una sintaxis rota en un .js con import/export
            # (lo prueba como CommonJS, falla y no lo reintenta como módulo): se copia a .mjs.
            if ruta.endswith(".js") and re.search(r"^\s*(import|export)\b", texto, re.M):
                with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False, encoding="utf-8") as f:
                    f.write(texto)
                    objetivo = temporal = f.name
            r = correr([node, "--check", objetivo])
            if temporal:
                os.unlink(temporal)
            if r.returncode != 0:
                salida = (r.stderr or r.stdout).strip().replace(temporal or "\0", ruta)
                errores.append("`node --check` falla:\n" + "\n".join(salida.splitlines()[:6]))
    elif ruta.endswith(".po"):
        if not py:
            avisos.append("no se revisó el catálogo: no hay venv con Babel")
        else:
            r = correr([py, "-c", PROBAR_PO, ruta])
            if r.returncode != 0:
                errores.append("Babel no puede leer el catálogo:\n" + r.stderr.strip()[-400:])
            else:
                fuzzy = json.loads(r.stdout or "[]")
                if fuzzy:
                    avisos.append(
                        "%d entradas `fuzzy` (en tiempo de ejecución NO se usan: la persona vería el español). "
                        "Corrige y quita la marca antes de commitear: %s"
                        % (len(fuzzy), "; ".join("«%s»" % f[:60] for f in fuzzy[:5])))
    return errores, avisos


def main():
    try:
        datos = json.load(sys.stdin)
    except Exception:
        return
    entrada = datos.get("tool_input") or {}
    ruta = entrada.get("file_path") or entrada.get("path") or ""
    if not ruta or not os.path.isfile(ruta):
        return
    errores, avisos = revisar(os.path.abspath(ruta))
    nombre = os.path.basename(ruta)
    if errores:
        sys.stderr.write("Revisión de %s (.claude/hooks/verificar_edicion.py):\n- %s\n"
                         % (nombre, "\n- ".join(errores)))
        if avisos:
            sys.stderr.write("Además:\n- " + "\n- ".join(avisos) + "\n")
        sys.exit(2)
    if avisos:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "Revisión de %s: %s" % (nombre, " / ".join(avisos)),
        }}))


if __name__ == "__main__":
    main()
