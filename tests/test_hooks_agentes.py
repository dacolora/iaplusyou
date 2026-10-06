"""Los hooks de .claude/hooks/ frenan lo que deben y dejan pasar el trabajo normal.

Cada caso bloqueado viene de un incidente real (ver el docstring de cada hook);
cada caso permitido es algo que las conversaciones hacen todos los días y que
un hook demasiado celoso trabaría.
"""
import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUARDAS = os.path.join(RAIZ, ".claude", "hooks", "guardas.py")
VERIFICAR = os.path.join(RAIZ, ".claude", "hooks", "verificar_edicion.py")
PYTHON = shutil.which("python3") or sys.executable


def _hook(script, payload, cwd=None):
    r = subprocess.run([PYTHON, script], input=json.dumps(payload), capture_output=True,
                       text=True, cwd=cwd or RAIZ, timeout=60)
    return r.returncode, r.stdout, r.stderr


def bash(comando, cwd=None):
    return _hook(GUARDAS, {"tool_name": "Bash", "tool_input": {"command": comando},
                           "cwd": cwd or RAIZ}, cwd=cwd)


def git(cwd, *args):
    subprocess.run(["git", "-c", "protocol.file.allow=always", *args], cwd=cwd, check=True,
                   capture_output=True, text=True)


@pytest.fixture
def repos(tmp_path):
    """Un «iaplusyou» de juguete (con dashboard.py) y un worktree suyo."""
    principal = tmp_path / "principal"
    principal.mkdir()
    git(principal, "init", "-q", "-b", "main")
    git(principal, "config", "user.email", "t@t")
    git(principal, "config", "user.name", "t")
    (principal / "dashboard.py").write_text("x = 1\n")
    (principal / "notas.txt").write_text("hola\n")
    git(principal, "add", ".")
    git(principal, "commit", "-q", "-m", "inicio")
    worktree = tmp_path / "wt"
    git(principal, "worktree", "add", "-q", str(worktree), "-b", "rama")
    return principal, worktree


# ── Llaves ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("comando", [
    "cat .env",
    "head -5 clientes/happyflops/.env",
    "grep ANTHROPIC .env",
    "printenv",
    "env",
    "env | sort",
    "echo $ANTHROPIC_API_KEY",
    "diff .env.example .env",
    "cat clientes/x/meta.json",
    "jq . clientes/x/meta.json",
    "jq .page_access_token clientes/x/meta.json",
    "ssh deploy@app.creatvmachine.com 'cat /home/deploy/iaplusyou/.env'",
])
def test_bloquea_lo_que_imprime_llaves(comando):
    codigo, _, err = bash(comando)
    assert codigo == 2, comando
    assert "BLOQUEADO" in err


@pytest.mark.parametrize("comando", [
    "cut -d= -f1 .env",
    "grep -c '^ANTHROPIC_API_KEY=' .env",
    "grep -q APIFY .env && echo sí",
    "cat .env.example",
    "source .env && venv/bin/python3 worker.py",
    "ls -la .env",
    "jq '.ad_account_id' clientes/x/meta.json",
    "jq keys clientes/x/meta.json",
    "env PYTHONPATH=. venv/bin/python3 -m pytest -q",
    "echo $HOME",
])
def test_deja_pasar_lo_que_no_imprime_llaves(comando):
    codigo, _, err = bash(comando)
    assert codigo == 0, (comando, err)


def test_read_y_grep_de_llaves():
    assert _hook(GUARDAS, {"tool_name": "Read", "tool_input": {"file_path": "/x/.env"}})[0] == 2
    assert _hook(GUARDAS, {"tool_name": "Read", "tool_input": {"file_path": "/x/.env.example"}})[0] == 0
    assert _hook(GUARDAS, {"tool_name": "Read", "tool_input": {"file_path": "/x/dashboard.py"}})[0] == 0
    assert _hook(GUARDAS, {"tool_name": "Grep", "tool_input": {
        "pattern": "KEY", "path": "/x/.env", "output_mode": "content"}})[0] == 2
    assert _hook(GUARDAS, {"tool_name": "Grep", "tool_input": {
        "pattern": "KEY", "path": "/x/.env", "output_mode": "count"}})[0] == 0


# ── Stash y push ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("comando", [
    "git stash", "git stash pop", "git stash clear", "git stash drop", "git stash -u",
    "git push --force origin main", "git push -f", "git push origin +main",
])
def test_bloquea_stash_y_push_forzado(comando):
    assert bash(comando)[0] == 2, comando


@pytest.mark.parametrize("comando", [
    "git stash list", "git stash show -p stash@{1}", 'git stash push -u -m "capa-agentes-wip"',
    "git stash apply 3f2a9c1", "git push origin capa-agentes", "git push --force origin rama-propia",
    "git push", "git status && git log --oneline -3",
])
def test_deja_pasar_stash_con_nombre_y_push_normal(comando):
    codigo, _, err = bash(comando)
    assert codigo == 0, (comando, err)


# ── Checkout principal ───────────────────────────────────────────────────────

@pytest.mark.parametrize("comando", [
    "git reset --hard", "git reset --hard origin/main", "git checkout -- notas.txt",
    "git checkout .", "git clean -fd", "git restore notas.txt", "git checkout rama",
    "git switch rama", "git add -A", "git add .", "git commit -am 'x'",
])
def test_bloquea_lo_destructivo_en_el_checkout_principal(repos, comando):
    principal, _ = repos
    codigo, _, err = bash(comando, cwd=str(principal))
    assert codigo == 2, comando
    assert "checkout principal" in err


@pytest.mark.parametrize("comando", [
    "git reset --hard", "git checkout -- notas.txt", "git clean -fd", "git add -A", "git checkout main",
])
def test_en_un_worktree_es_trabajo_propio(repos, comando):
    _, worktree = repos
    codigo, _, err = bash(comando, cwd=str(worktree))
    assert codigo == 0, (comando, err)


def test_tambien_ve_cd_y_menos_c_hacia_el_principal(repos):
    principal, worktree = repos
    assert bash("cd %s && git reset --hard" % principal, cwd=str(worktree))[0] == 2
    assert bash("git -C %s clean -fdx" % principal, cwd=str(worktree))[0] == 2
    assert bash("git -C %s status" % principal, cwd=str(worktree))[0] == 0


@pytest.mark.parametrize("comando", [
    "git checkout main", "git restore --staged notas.txt", "git clean -n", "git add notas.txt",
    "git status", "git diff", "git log -3", "git fetch -q origin",
])
def test_lo_cotidiano_pasa_en_el_principal(repos, comando):
    principal, _ = repos
    codigo, _, err = bash(comando, cwd=str(principal))
    assert codigo == 0, (comando, err)


def test_un_heredoc_que_menciona_comandos_no_es_un_comando(repos):
    principal, _ = repos
    comando = textwrap.dedent("""\
        git commit -F- <<'EOF'
        Guardas: frenar git reset --hard y git stash pop en el principal
        EOF""")
    codigo, _, err = bash(comando, cwd=str(principal))
    assert codigo == 0, err
    comando = 'git commit -m "$(cat <<\'EOF\'\nNo usar git checkout . ni cat .env\nEOF\n)"'
    codigo, _, err = bash(comando, cwd=str(principal))
    assert codigo == 0, err
    # Líneas del cuerpo que, leídas como comandos, se bloquearían:
    comando = "cat > notas.md <<'EOF'\ncat .env\ngit reset --hard\nEOF\nwc -l notas.md"
    codigo, _, err = bash(comando, cwd=str(principal))
    assert codigo == 0, err
    # …y lo que viene DESPUÉS del heredoc sí se revisa.
    assert bash("cat > notas.md <<'EOF'\nhola\nEOF\ngit reset --hard", cwd=str(principal))[0] == 2


# ── ssh al VPS ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("comando", [
    "ssh deploy@app.creatvmachine.com 'set -e; cd iaplusyou && git pull && sudo systemctl restart creatv-worker'",
    "ssh deploy@app.creatvmachine.com 'python3 chequeo.py' ; ssh root@app.creatvmachine.com 'systemctl restart iaplusyou'",
    'ssh deploy@app.creatvmachine.com "cd /home/deploy/iaplusyou && git stash && git pull origin main"',
    "ssh deploy@app.creatvmachine.com 'cd iaplusyou && git reset --hard origin/main'",
    "ssh deploy@app.creatvmachine.com 'cd iaplusyou && git checkout .'",
])
def test_bloquea_lo_peligroso_en_el_vps(comando):
    assert bash(comando)[0] == 2, comando


@pytest.mark.parametrize("comando", [
    "ssh deploy@app.creatvmachine.com 'cd iaplusyou && venv/bin/python3 hay_vivas.py' && "
    "ssh root@app.creatvmachine.com 'systemctl restart iaplusyou creatv-worker'",
    "ssh deploy@app.creatvmachine.com 'cd iaplusyou && git pull origin main && venv/bin/alembic upgrade head'",
    "ssh deploy@app.creatvmachine.com 'cd iaplusyou && git log --oneline -3 && git stash list'",
    "ssh -o ConnectTimeout=5 root@app.creatvmachine.com 'systemctl is-active creatv-app creatv-worker'",
    "ssh deploy@app.creatvmachine.com 'python3 -c \"import a; a.b()\"'",
])
def test_deja_pasar_el_despliegue_bien_hecho(comando):
    codigo, _, err = bash(comando)
    assert codigo == 0, (comando, err)


# ── Commit ───────────────────────────────────────────────────────────────────

def test_commit_con_marcas_de_conflicto(repos):
    _, worktree = repos
    (worktree / "notas.txt").write_text("<<<<<<< HEAD\na\n=======\nb\n>>>>>>> main\n")
    git(worktree, "add", "notas.txt")
    codigo, _, err = bash("git commit -m 'merge'", cwd=str(worktree))
    assert codigo == 2 and "conflicto" in err


def test_commit_con_po_fuzzy(repos):
    _, worktree = repos
    (worktree / "messages.po").write_text(
        'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
        '#, fuzzy\nmsgid "Empezar de cero"\nmsgstr "Check at least one valid destination"\n')
    git(worktree, "add", "messages.po")
    codigo, _, err = bash("git commit -m 'catálogo'", cwd=str(worktree))
    assert codigo == 2 and "fuzzy" in err


# Las llaves de prueba se arman en tiempo de ejecución: escritas enteras, este mismo
# archivo no se podría commitear (el hook las frenaría, con razón).
LLAVE_ANTHROPIC = "sk-" + "ant-" + "api03-" + "Q" * 40
LLAVE_SHOPIFY = "shp" + "at_" + "a1" * 16


@pytest.mark.parametrize("contenido", [
    "ANTHROPIC = '%s'\n" % LLAVE_ANTHROPIC,
    "tienda = {'token': '%s'}\n" % LLAVE_SHOPIFY,
    "URL = 'postgresql://creatv:" + "clave_de_verdad" + "@db.ejemplo.com/creatv'\n",
    "WAVESPEED_API_KEY = '" + "k9" * 20 + "'\n",
])
def test_commit_con_una_llave(repos, contenido):
    _, worktree = repos
    (worktree / "config_local.py").write_text(contenido)
    git(worktree, "add", "config_local.py")
    codigo, _, err = bash("git commit -m 'config'", cwd=str(worktree))
    assert codigo == 2 and "llave" in err
    assert "Q" * 40 not in err and "a1" * 16 not in err  # el aviso nunca repite el valor
    assert bash("git commit -m 'config'  # llaves-revisadas", cwd=str(worktree))[0] == 0


def test_llave_falsa_marcada_en_una_prueba(repos):
    _, worktree = repos
    (worktree / "test_x.py").write_text("FALSA = '%s'  # llave-de-prueba\n" % LLAVE_ANTHROPIC)
    git(worktree, "add", "test_x.py")
    codigo, _, err = bash("git commit -m 'prueba'", cwd=str(worktree))
    assert codigo == 0, err


def test_commit_de_un_env_forzado(repos):
    _, worktree = repos
    (worktree / ".env").write_text("NADA=1\n")
    git(worktree, "add", "-f", ".env")
    codigo, _, err = bash("git commit -m 'env'", cwd=str(worktree))
    assert codigo == 2 and ".env" in err


def test_commit_normal_pasa(repos):
    _, worktree = repos
    (worktree / "notas.txt").write_text("chao\n")
    git(worktree, "add", "notas.txt")
    codigo, _, err = bash("git commit -m 'notas'", cwd=str(worktree))
    assert codigo == 0, err


def test_merge_que_revierte_un_submodulo(tmp_path, repos):
    """El incidente del 2026-09-28: main movió meta_ads y el merge lo devolvió."""
    principal, worktree = repos
    sub = tmp_path / "sub"
    sub.mkdir()
    git(sub, "init", "-q", "-b", "main")
    git(sub, "config", "user.email", "t@t")
    git(sub, "config", "user.name", "t")
    (sub / "a").write_text("1")
    git(sub, "add", ".")
    git(sub, "commit", "-q", "-m", "c1")
    viejo = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sub, capture_output=True, text=True).stdout.strip()
    (sub / "a").write_text("2")
    git(sub, "commit", "-qam", "c2")
    nuevo = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sub, capture_output=True, text=True).stdout.strip()

    git(principal, "update-index", "--add", "--cacheinfo", "160000,%s,meta_ads" % viejo)
    git(principal, "commit", "-q", "-m", "submódulo en c1")
    git(worktree, "merge", "-q", "main")  # la rama arranca con c1 y nunca lo toca
    git(principal, "update-index", "--cacheinfo", "160000,%s,meta_ads" % nuevo)
    git(principal, "commit", "-q", "-m", "main mueve meta_ads a c2")
    (worktree / "notas.txt").write_text("cambio de la rama\n")
    git(worktree, "commit", "-qam", "trabajo en la rama")

    git(worktree, "merge", "--no-commit", "--no-ff", "main")
    # Lo que hace `git add -A` con el submódulo todavía en el commit viejo:
    git(worktree, "update-index", "--cacheinfo", "160000,%s,meta_ads" % viejo)
    codigo, _, err = bash("git commit -m 'merge main'", cwd=str(worktree))
    assert codigo == 2 and "meta_ads" in err
    assert bash("git commit -m 'merge main'  # submodulo-intencional", cwd=str(worktree))[0] == 0
    git(worktree, "update-index", "--cacheinfo", "160000,%s,meta_ads" % nuevo)
    codigo, _, err = bash("git commit -m 'merge main'", cwd=str(worktree))
    assert codigo == 0, err


# ── Verificar tras editar ────────────────────────────────────────────────────

@pytest.fixture
def proyecto(tmp_path):
    """Repo de juguete con dashboard.py y el venv de los tests (para Jinja y Babel)."""
    raiz = tmp_path / "proyecto"
    (raiz / "templates").mkdir(parents=True)
    git(raiz, "init", "-q", "-b", "main")
    git(raiz, "config", "user.email", "t@t")
    git(raiz, "config", "user.name", "t")
    (raiz / "dashboard.py").write_text("x = 1\n")
    (raiz / "templates" / "base.html").write_text("<script>var a = '<div>';</script>\n<div></div>\n")
    git(raiz, "add", ".")
    git(raiz, "commit", "-q", "-m", "inicio")
    (raiz / "venv").symlink_to(sys.prefix)
    return raiz


def editar(ruta, contenido):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(contenido, encoding="utf-8")
    return _hook(VERIFICAR, {"tool_name": "Edit", "tool_input": {"file_path": str(ruta)}})


def test_python_que_no_compila(proyecto):
    codigo, _, err = editar(proyecto / "malo.py", "def f(:\n    pass\n")
    assert codigo == 2 and "no compila" in err
    assert editar(proyecto / "bueno.py", "def f():\n    return 1\n")[0] == 0


def test_macro_sin_cerrar_su_div(proyecto):
    codigo, _, err = editar(proyecto / "templates" / "_tarjetas.html",
                            "{% macro tarjeta(x) %}<div class='generado'><p>{{ x }}</p>{% endmacro %}\n")
    assert codigo == 2 and "tarjeta" in err
    assert editar(proyecto / "templates" / "_bien.html",
                  "{% macro tarjeta(x) %}<div class='generado'>{{ x }}</div>{% endmacro %}\n")[0] == 0


def test_div_que_se_sale_de_la_macro(proyecto):
    """La forma exacta del 2026-09-28: el </div> quedó después del final de la macro.

    El balance del archivo no cambia (sigue siendo cero); solo la macro lo delata."""
    ruta = proyecto / "templates" / "_crear_tarjetas.html"
    ruta.write_text("{% macro tarjeta() %}<div class='generado'><template>x</template></div>{% endmacro %}\n")
    git(proyecto, "add", ".")
    git(proyecto, "commit", "-q", "-m", "tarjetas")
    codigo, _, err = editar(ruta, "{% macro tarjeta() %}<div class='generado'><template>x</template>"
                                  "{% endmacro %}</div>\n")
    assert codigo == 2 and "tarjeta" in err


def test_plantilla_que_jinja_no_lee(proyecto):
    codigo, _, err = editar(proyecto / "templates" / "_rota.html", "{% if x %}<p>sin cerrar</p>\n")
    assert codigo == 2 and "Jinja" in err


def test_balance_contra_head_no_castiga_lo_heredado(proyecto):
    base = proyecto / "templates" / "base.html"
    assert editar(base, "<script>var a = '<div>';</script>\n<div>otro texto</div>\n")[0] == 0
    codigo, _, err = editar(base, "<script>var a = '<div>';</script>\n<div><div>otro texto</div>\n")
    assert codigo == 2 and "HEAD" in err


def test_js_roto_aunque_sea_modulo(proyecto):
    if not shutil.which("node"):
        pytest.skip("sin node")
    codigo, _, err = editar(proyecto / "static" / "editor" / "x.js", "export const a = ;\n")
    assert codigo == 2 and "node --check" in err
    assert editar(proyecto / "static" / "editor" / "y.js", "export const a = 1;\n")[0] == 0


def test_po_con_fuzzy_avisa_sin_bloquear(proyecto):
    codigo, salida, _ = editar(proyecto / "translations" / "en" / "LC_MESSAGES" / "messages.po",
                               'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
                               '#, fuzzy\nmsgid "Hola"\nmsgstr "Hello"\n')
    assert codigo == 0
    assert "fuzzy" in json.loads(salida)["hookSpecificOutput"]["additionalContext"]


def test_marcas_de_conflicto_en_cualquier_archivo(proyecto):
    codigo, _, err = editar(proyecto / "notas.md", "a\n<<<<<<< HEAD\nb\n=======\nc\n>>>>>>> main\n")
    assert codigo == 2 and "conflicto" in err


def test_fuera_del_proyecto_no_opina(tmp_path):
    otro = tmp_path / "otro"
    otro.mkdir()
    git(otro, "init", "-q")
    assert editar(otro / "malo.py", "def f(:\n")[0] == 0
