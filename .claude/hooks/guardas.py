"""PreToolUse (Bash | Read | Grep): frena lo que ya nos costó caro.

Cada guarda lleva el incidente que la justifica. Salir con 2 bloquea la
herramienta y le muestra a Claude el motivo (stderr); con 0 la deja pasar.
Una guarda que no logra decidir (payload raro, git que no responde) deja
pasar: es una red de seguridad, no un muro, y nunca debe trabar el trabajo
por un error propio.

Corre con el python3 del sistema (3.9): solo biblioteca estándar.
"""
import json
import os
import re
import shlex
import subprocess
import sys

# ── Llaves ───────────────────────────────────────────────────────────────────
# Una llave impresa queda en la transcripción. Naia tuvo que rotar la clave de
# su base de producción por un `sed` que no casó e imprimió la línea entera.
SECRETO_EXACTO = {
    "token_youtube.json", "token_tiktok.json", "meta.json", "meta_app.json",
    "id_rsa", "id_ed25519",
}
ENV_PLANTILLAS = {".env.example", ".env.sample", ".env.template"}
LECTORES = {
    "cat", "less", "more", "head", "tail", "bat", "nl", "strings", "xxd", "od",
    "grep", "egrep", "fgrep", "rg", "ag", "awk", "gawk", "sed", "sort", "uniq",
    "jq", "tac", "rev", "fold", "column", "paste", "view", "vim", "vi", "nano",
    "cut", "diff", "base64", "openssl", "python", "python3", "node", "ruby", "perl",
}
VARIABLE_SECRETA = re.compile(r"\$\{?[A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD|PASS|CLAVE)[A-Z0-9_]*\}?")

# ── Git ──────────────────────────────────────────────────────────────────────
VPS = "creatvmachine.com"


def es_secreto(ruta):
    base = os.path.basename(ruta.strip("'\""))
    if base in ENV_PLANTILLAS:
        return False
    if base == ".env" or base.startswith(".env."):
        return True
    if base in SECRETO_EXACTO:
        return True
    return base.endswith(".pem") or base.endswith(".p12")


HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def quitar_heredocs(texto):
    """El cuerpo de un heredoc es texto, no comandos: se descarta antes de leer.

    Sin esto, un `git commit -F- <<EOF` o un `python3 - <<EOF` que mencione
    `git reset --hard` en su texto se tomaría por el comando mismo."""
    salida = []
    lineas = texto.split("\n")
    i = 0
    while i < len(lineas):
        linea = lineas[i]
        salida.append(linea)
        pendientes = [(m.group(1) == "-", m.group(3)) for m in HEREDOC.finditer(linea)]
        i += 1
        for con_tabs, fin in pendientes:
            while i < len(lineas):
                actual = lineas[i].lstrip("\t") if con_tabs else lineas[i]
                i += 1
                if actual.strip() == fin:
                    break
    return "\n".join(salida)


def tokens_de(texto):
    lex = shlex.shlex(texto, posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    try:
        return list(lex)
    except ValueError:
        # Comillas sin cerrar: se parte a lo bruto (mejor una guarda de menos
        # que trabar un comando legítimo).
        return re.findall(r"&&|\|\||[;|&\n()]|[^\s;|&()]+", texto)


def operador(tok):
    """Normaliza un token de puntuación a operador, o None si es una redirección."""
    if not tok or any(c not in "();<>|&\n" for c in tok):
        return None
    if set(tok) <= set("<>&") and ("<" in tok or ">" in tok):
        return None  # redirección: >, >>, >&, <, <<
    if "&&" in tok:
        return "&&"
    if "||" in tok:
        return "||"
    if "|" in tok:
        return "|"
    if ";" in tok or "\n" in tok:
        return ";"
    if "&" in tok:
        return "&"
    return "("  # paréntesis de subshell: separa sin cambiar el operador previo


def segmentos(texto):
    """[(operador_previo, [tokens])]; el operador es &&, ||, |, ; o & (None al inicio)."""
    salida = []
    previo = None
    actual = []
    for t in tokens_de(quitar_heredocs(texto.replace("\\\n", " "))):
        op = operador(t)
        if op is None:
            actual.append(t)
            continue
        if actual:
            salida.append((previo, actual))
            actual = []
        if op != "(":
            previo = op
    if actual:
        salida.append((previo, actual))
    return salida


def sin_prefijos(toks):
    """Quita asignaciones VAR=x, `sudo`, `command`, `time`, `nohup`, `env X=y`."""
    i = 0
    while i < len(toks):
        t = toks[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", t):
            i += 1
        elif t in ("sudo", "command", "time", "nohup", "exec", "builtin"):
            i += 1
        elif t == "env" and i + 1 < len(toks) and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", toks[i + 1]):
            i += 1
        else:
            break
    return toks[i:]


def bloquear(motivo):
    sys.stderr.write("BLOQUEADO por .claude/hooks/guardas.py\n\n" + motivo.strip() + "\n")
    sys.exit(2)


# ── Llaves ───────────────────────────────────────────────────────────────────

def revisar_llaves(toks):
    if not toks:
        return
    cmd = os.path.basename(toks[0])
    args = toks[1:]
    if cmd == "printenv" or (cmd == "env" and not args) or (cmd == "export" and args[:1] == ["-p"]) \
            or (cmd == "declare" and any(a in ("-x", "-p") for a in args)) or (cmd == "set" and not args):
        bloquear(
            "Este comando imprime todas las variables de entorno, llaves incluidas.\n"
            "Para saber si una existe: `test -n \"$NOMBRE\" && echo sí`."
        )
    if cmd in ("echo", "printf") and any(VARIABLE_SECRETA.search(a) for a in args):
        bloquear(
            "Esto imprime el valor de una llave. Para saber si existe: `test -n \"$NOMBRE\" && echo sí`."
        )
    secretos = [a for a in args if not a.startswith("-") and es_secreto(a)]
    if not secretos or cmd not in LECTORES:
        return
    banderas = "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))
    largas = {a for a in args if a.startswith("--")}
    if cmd in ("grep", "egrep", "fgrep", "rg") and (
            set(banderas) & set("clLq") or largas & {"--count", "--files-with-matches", "--quiet", "--files-without-match"}):
        return
    if cmd == "cut" and re.search(r"(^|\s)-f\s*1(\s|$)", " ".join(args)) and "=" in " ".join(args):
        return
    if cmd == "diff" and ("q" in banderas or "--brief" in largas):
        return
    if cmd == "jq":
        filtro = next((a for a in args if not a.startswith("-") and not es_secreto(a)), ".")
        if filtro == "keys" or (re.match(r"^\.[A-Za-z_][A-Za-z0-9_.]*$", filtro)
                                and not re.search(r"token|secret|key|clave|password", filtro, re.I)):
            return
    bloquear(
        "Este comando mostraría el contenido de un archivo con llaves: " + ", ".join(secretos) + ".\n"
        "Lo que se imprime queda en la transcripción. Para ver qué variables hay sin sus valores:\n"
        "  cut -d= -f1 .env\n"
        "Para saber si una existe: grep -c '^NOMBRE=' .env\n"
        "En un .json: jq 'keys' archivo.json, o jq '.campo' para un campo que no sea un token."
    )


# ── Git ──────────────────────────────────────────────────────────────────────

def git(cwd, *args):
    try:
        r = subprocess.run(("git", "-C", cwd) + args, capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def es_checkout_principal(cwd):
    """True si cwd es el checkout principal de iaplusyou (no un worktree ni un submódulo).

    Ahí trabajan varias conversaciones a la vez: lo que una deja sin guardar,
    otra lo puede borrar."""
    top = git(cwd, "rev-parse", "--show-toplevel")
    if not top or not os.path.isfile(os.path.join(top, "dashboard.py")):
        return False
    gd = git(cwd, "rev-parse", "--absolute-git-dir")
    cd = git(cwd, "rev-parse", "--git-common-dir")
    if not gd or not cd:
        return False
    if not os.path.isabs(cd):
        cd = os.path.join(top, cd)
    return os.path.realpath(gd) == os.path.realpath(cd)


def partir_git(toks):
    """(subcomando, args, dir_de_-C) de un `git …`, o None."""
    if not toks or os.path.basename(toks[0]) != "git":
        return None
    i = 1
    dir_c = None
    while i < len(toks) and toks[i].startswith("-"):
        if toks[i] == "-C" and i + 1 < len(toks):
            dir_c = toks[i + 1]
            i += 2
        elif toks[i] in ("-c", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(toks):
            i += 2
        else:
            i += 1
    if i >= len(toks):
        return None
    return toks[i], toks[i + 1:], dir_c


def destructivo(sub, args):
    """Motivo si el subcomando borra trabajo sin guardar, o None."""
    cortas = "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))
    if sub == "reset" and "--hard" in args:
        return "`git reset --hard` borra los cambios sin guardar"
    if sub == "clean" and ("f" in cortas or "--force" in args) and not ("n" in cortas or "--dry-run" in args):
        return "`git clean -f` borra archivos nuevos sin guardar"
    if sub == "restore":
        solo_staged = {"--staged", "-S"} & set(args) and not {"--worktree", "-W"} & set(args)
        if not solo_staged:
            return "`git restore` descarta los cambios sin guardar de esos archivos"
    if sub == "add" and ({"-A", "--all", "."} & set(args) or "A" in cortas):
        return ("`git add -A` / `git add .` mete en el commit lo que otras conversaciones dejaron sin guardar "
                "(agrega rutas explícitas)")
    if sub == "commit" and ("a" in cortas or "--all" in args):
        return "`git commit -a` mete en el commit lo que otras conversaciones dejaron sin guardar (agrega rutas explícitas)"
    if sub == "checkout":
        if "--" in args or "." in args or "-f" in args or "--force" in args:
            return "`git checkout -- …` / `git checkout .` descarta cambios sin guardar"
        if args and args != ["main"]:
            return "cambiar de rama en el checkout principal cambia el piso de todas las conversaciones que trabajan ahí"
    if sub == "switch" and args and args != ["main"]:
        return "cambiar de rama en el checkout principal cambia el piso de todas las conversaciones que trabajan ahí"
    return None


def revisar_stash(args):
    """La pila de stash es UNA para el checkout principal y todos los worktrees."""
    sub = args[0] if args and not args[0].startswith("-") else "push"
    resto = args[1:] if args and not args[0].startswith("-") else args
    if sub in ("list", "show", "create", "store"):
        return
    motivo = None
    if sub == "clear":
        motivo = "`git stash clear` borra los stash de TODAS las conversaciones"
    elif sub == "pop":
        motivo = "`git stash pop` puede sacar el stash de otra conversación (la pila es compartida)"
    elif sub in ("drop", "apply") and not any(re.match(r"^(stash@\{\d+\}|[0-9a-f]{7,40})$", a) for a in resto):
        motivo = "`git stash %s` sin un stash explícito toma el de arriba, que puede ser de otra conversación" % sub
    elif sub in ("push", "save") and not ({"-m", "--message"} & set(resto)) and sub != "save":
        motivo = "un `git stash` sin nombre no se puede encontrar después entre los de otras conversaciones"
    if motivo:
        bloquear(
            motivo + ".\n"
            "Mejor un commit temporal (WIP) en tu rama. Si de verdad hace falta un stash:\n"
            "  git stash push -u -m \"<etiqueta única>\"  y luego  git stash apply <sha>  (nunca pop)."
        )


def revisar_push(args):
    forzado = any(a in ("-f", "--force", "--force-with-lease") or a.startswith("--force-with-lease=")
                  for a in args)
    if not forzado:
        positivos = [a for a in args if not a.startswith("-")]
        forzado = any(p.startswith("+") for p in positivos[1:])
    if not forzado:
        return
    positivos = [a for a in args if not a.startswith("-")]
    ramas = positivos[1:]
    if not ramas or any(re.search(r"(^|:|\+)(refs/heads/)?main$", r) for r in ramas):
        bloquear(
            "Push forzado a `main`: borraría los commits que otras conversaciones ya subieron.\n"
            "Trae main (`git fetch && git merge origin/main`) y sube sin forzar."
        )


def conflictos_staged(cwd):
    diff = git(cwd, "diff", "--cached", "-U0", "--no-color")
    if not diff:
        return []
    malos = []
    archivo = None
    for linea in diff.splitlines():
        if linea.startswith("+++ "):
            archivo = linea[6:] if linea.startswith("+++ b/") else linea[4:]
        elif re.match(r"^\+(<{7} |>{7} |<{7}$|>{7}$)", linea):
            if archivo not in malos:
                malos.append(archivo)
    return malos


def puntero(cwd, ref, ruta):
    out = git(cwd, "ls-tree", ref, ruta)
    if not out:
        return None
    partes = out.split()
    return partes[2] if len(partes) >= 3 and partes[1] == "commit" else None


def submodulos_revertidos(cwd):
    """Submódulos que el merge en curso devolvería a un commit viejo.

    2026-09-28: un merge de main se cerró con `git add -A` y `meta_ads` todavía
    en el commit viejo; el commit de merge devolvió el submódulo sin que nadie
    lo viera. Regla de tres vías: si nuestra rama nunca tocó el puntero (ours ==
    base) y main sí (theirs != base), lo staged tiene que ser lo de main."""
    gd = git(cwd, "rev-parse", "--absolute-git-dir")
    if not gd or not os.path.exists(os.path.join(gd, "MERGE_HEAD")):
        return []
    base = git(cwd, "merge-base", "HEAD", "MERGE_HEAD")
    if not base:
        return []
    staged = git(cwd, "ls-files", "-s") or ""
    malos = []
    for linea in staged.splitlines():
        partes = linea.split(None, 3)
        if len(partes) < 4 or partes[0] != "160000":
            continue
        sha, ruta = partes[1], partes[3]
        ours, theirs, b = puntero(cwd, "HEAD", ruta), puntero(cwd, "MERGE_HEAD", ruta), puntero(cwd, base, ruta)
        if ours == b and theirs and theirs != b and sha != theirs:
            malos.append((ruta, sha[:8], theirs[:8]))
    return malos


def po_con_fuzzy(cwd):
    nombres = git(cwd, "diff", "--cached", "--name-only") or ""
    malos = []
    for ruta in nombres.splitlines():
        if not ruta.endswith(".po"):
            continue
        contenido = git(cwd, "show", ":" + ruta) or ""
        entradas = contenido.split("\n\n")
        n = sum(1 for e in entradas[1:] if re.search(r"^#,.*\bfuzzy\b", e, re.M) and not e.lstrip().startswith("#~"))
        if n:
            malos.append((ruta, n))
    return malos


def revisar_commit(cwd, comando):
    conflictos = conflictos_staged(cwd)
    if conflictos:
        bloquear("Hay marcas de conflicto (<<<<<<< / >>>>>>>) en lo que vas a commitear:\n  "
                 + "\n  ".join(conflictos))
    if "submodulo-intencional" not in comando:
        revertidos = submodulos_revertidos(cwd)
        if revertidos:
            bloquear(
                "Este commit de merge devuelve un submódulo a un commit viejo:\n"
                + "".join("  %s: staged %s, main lo tiene en %s\n" % r for r in revertidos)
                + "Corre `git submodule update --init --recursive` y `git add <submódulo>` antes de commitear.\n"
                "Si el cambio es a propósito, agrega `# submodulo-intencional` al final del comando."
            )
    fuzzy = po_con_fuzzy(cwd)
    if fuzzy:
        bloquear(
            "El catálogo que vas a commitear tiene entradas `fuzzy`, que en tiempo de ejecución NO se usan\n"
            "(la persona vería el español):\n"
            + "".join("  %s: %d entradas fuzzy\n" % f for f in fuzzy)
            + "Corrige cada traducción, quita la marca `#, fuzzy` y compila (`catalogo_i18n.py compilar`)."
        )


# ── ssh al VPS ───────────────────────────────────────────────────────────────

def partir_ssh(toks):
    """(host, comando_remoto) de un `ssh … host 'comando'`, o None."""
    if not toks or os.path.basename(toks[0]) != "ssh":
        return None
    con_valor = set("BbcDEeFIiJLlmOoPpQRSWw")
    i = 1
    while i < len(toks) and toks[i].startswith("-"):
        bandera = toks[i]
        i += 2 if len(bandera) == 2 and bandera[1] in con_valor else 1
    if i >= len(toks):
        return None
    return toks[i], " ".join(toks[i + 1:])


REINICIO = re.compile(r"\bsystemctl\b[^\n]*\b(restart|stop|start|reload)\b")


def revisar_remoto(host, remoto):
    for _prev, toks in segmentos(remoto):
        toks = sin_prefijos(toks)
        revisar_llaves(toks)
        g = partir_git(toks)
        if not g:
            continue
        sub, args, _ = g
        if (sub == "stash" and args[:1] not in (["list"], ["show"])) or (
                sub in ("reset", "clean", "restore", "checkout") and destructivo(sub, args)):
            bloquear(
                "`git %s` en el servidor (%s).\n"
                "El VPS tiene datos de happyflops versionados (clientes/*/productos*): un stash, reset o checkout\n"
                "los puede borrar o dejar escondidos. Respáldalos primero y pídele a Daniel que lo corra él." % (sub, host)
            )
    if REINICIO.search(remoto) and ";" in remoto:
        bloquear(
            "Comando remoto con `;` y un reinicio de servicios.\n"
            "El 2026-09-28 un `;` hizo que el reinicio corriera aunque la comprobación de la cola había fallado\n"
            "(`set -e` no corta dentro de una lista con &&): el worker se reinició con 3 imágenes vivas.\n"
            "Reglas: la comprobación de tareas vivas va en un `ssh` PROPIO; el resto solo corre si ese ssh\n"
            "devolvió 0 (`ssh … && ssh …`); dentro del comando remoto, solo `&&`."
        )


# ── Entrada ──────────────────────────────────────────────────────────────────

def revisar_bash(comando, cwd):
    actual = cwd
    for previo, toks in segmentos(comando):
        toks = sin_prefijos(toks)
        if not toks:
            continue
        cabeza = os.path.basename(toks[0])
        if cabeza == "cd" and len(toks) > 1:
            destino = os.path.expanduser(toks[1])
            actual = destino if os.path.isabs(destino) else os.path.join(actual, destino)
            continue
        revisar_llaves(toks)
        ssh = partir_ssh(toks)
        if ssh:
            host, remoto = ssh
            revisar_remoto(host, remoto)
            if REINICIO.search(remoto) and previo in (";", "\n", "|", "||", "&"):
                bloquear(
                    "Un `ssh` que reinicia servicios encadenado con `%s`: corre aunque lo anterior haya fallado.\n"
                    "Encadena los ssh con `&&` para que el reinicio solo pase si la comprobación de la cola salió bien."
                    % previo.replace("\n", "salto de línea")
                )
            continue
        g = partir_git(toks)
        if not g:
            continue
        sub, args, dir_c = g
        donde = actual
        if dir_c:
            dir_c = os.path.expanduser(dir_c)
            donde = dir_c if os.path.isabs(dir_c) else os.path.join(actual, dir_c)
        if sub == "stash":
            revisar_stash(args)
            continue
        if sub == "push":
            revisar_push(args)
            continue
        motivo = destructivo(sub, args)
        if motivo and es_checkout_principal(donde):
            bloquear(
                motivo + ", y estás en el checkout principal (" + donde + ").\n"
                "Ahí trabajan varias conversaciones a la vez: lo que se pierda puede ser de otra.\n"
                "Trabaja en un worktree (.claude/worktrees/<nombre>) o pídele a Daniel que lo corra él."
            )
        if sub == "commit":
            revisar_commit(donde, comando)


def main():
    try:
        datos = json.load(sys.stdin)
    except Exception:
        return
    herramienta = datos.get("tool_name", "")
    entrada = datos.get("tool_input") or {}
    cwd = datos.get("cwd") or os.getcwd()
    if herramienta == "Bash":
        revisar_bash(entrada.get("command") or "", cwd)
    elif herramienta == "Read":
        ruta = entrada.get("file_path") or ""
        if es_secreto(ruta):
            bloquear(
                "Leer %s pondría sus llaves en la transcripción.\n"
                "Para ver qué variables hay sin sus valores: `cut -d= -f1 .env`." % os.path.basename(ruta)
            )
    elif herramienta == "Grep":
        ruta = entrada.get("path") or ""
        if es_secreto(ruta) and entrada.get("output_mode") == "content":
            bloquear("Buscar con contenido dentro de %s imprimiría llaves. Usa output_mode \"count\"."
                     % os.path.basename(ruta))


if __name__ == "__main__":
    main()
