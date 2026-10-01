"""La guía para agentes sigue corta, con una skill por área, y un solo contrato.

Hasta el 2026-10-01 CLAUDE.md pesaba 150 KB (unos 40 000 tokens en cada sesión y en
cada subagente) y AGENTS.md era una copia vieja que ya decía otra cosa. Estas pruebas
impiden que vuelva a pasar: lo nuevo de un área va a su skill.
"""
import json
import os
import re

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS = os.path.join(RAIZ, ".claude", "skills")
MAX_LINEAS_CONTRATO = 250


def contrato():
    return open(os.path.join(RAIZ, "CLAUDE.md"), encoding="utf-8").read()


def frontmatter(ruta):
    texto = open(ruta, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n", texto, re.S)
    assert m, "%s no empieza con frontmatter" % ruta
    datos = {}
    for linea in m.group(1).splitlines():
        clave, _, valor = linea.partition(":")
        valor = valor.strip()
        datos[clave.strip()] = json.loads(valor) if valor.startswith('"') else valor
    return datos


def areas():
    return sorted(d for d in os.listdir(SKILLS) if os.path.isfile(os.path.join(SKILLS, d, "SKILL.md")))


def test_el_contrato_sigue_corto():
    lineas = contrato().count("\n")
    assert lineas <= MAX_LINEAS_CONTRATO, (
        "CLAUDE.md tiene %d líneas (tope %d): lo nuevo de un área va a su skill en .claude/skills/<área>/SKILL.md"
        % (lineas, MAX_LINEAS_CONTRATO))


def test_agents_md_es_el_mismo_contrato():
    agents = os.path.join(RAIZ, "AGENTS.md")
    assert os.path.islink(agents) and os.readlink(agents) == "CLAUDE.md", \
        "AGENTS.md debe ser un enlace a CLAUDE.md (Codex y Claude leen el mismo contrato)"


def test_cada_skill_tiene_nombre_y_descripcion():
    assert areas(), "no hay skills de área"
    for area in areas():
        datos = frontmatter(os.path.join(SKILLS, area, "SKILL.md"))
        assert datos.get("name") == area, area
        descripcion = datos.get("description") or ""
        assert 80 <= len(descripcion) <= 1024, (area, len(descripcion))
        assert "Cargar antes de" in descripcion, "%s: la descripción debe decir cuándo cargarla" % area


def test_la_tabla_del_contrato_y_las_skills_coinciden():
    en_tabla = set(re.findall(r"\(\.claude/skills/([a-z0-9-]+)/SKILL\.md\)", contrato()))
    assert en_tabla == set(areas()), {"sin fila en la tabla": set(areas()) - en_tabla,
                                      "fila sin skill": en_tabla - set(areas())}


def test_los_hooks_configurados_existen():
    ajustes = json.load(open(os.path.join(RAIZ, ".claude", "settings.json"), encoding="utf-8"))
    comandos = [h["command"] for grupo in ajustes["hooks"].values() for g in grupo for h in g["hooks"]]
    assert comandos
    for comando in comandos:
        for script in re.findall(r"\.claude/hooks/[a-z_]+\.py", comando):
            assert os.path.isfile(os.path.join(RAIZ, script)), script
