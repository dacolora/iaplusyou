# Relevo — holandés en Audios: falta desplegar a producción
**Escrito:** 2026-10-07 14:40 (hora de Bogotá) · **Rama / worktree:** `audios-holandes` (`.claude/worktrees/audios-holandes`) · **Spec o plan:** ninguno · **PR:** https://github.com/dacolora/iaplusyou/pull/9 (borrador)

## En un párrafo
Daniel pidió agregar el holandés (`nl`) a los idiomas de los audios (modo Audios de Crear y voces propias). El código y las pruebas están hechos, commiteados (`bcb5293`) y subidos a la rama `audios-holandes`, con el PR #9 abierto en borrador. **Falta solo desplegar a producción**: Daniel pidió «sal a pdn» y esa conversación (en la nube) no tiene `ssh` ni el submódulo `meta_ads`, así que no pudo. Esta conversación (la que corre en el computador de Daniel) sí debe poder: sigue la skill `despliegue`.

## Hecho, y cómo se verificó
- `audios.py`: `nl` al final de `IDIOMAS`, «Nederlands» en `NOMBRES_IDIOMA`, frase de muestra en holandés en `FRASES_MUESTRA` | verificado con: `venv/bin/python3 -m pytest -q tests/test_audios.py tests/test_fal_audio.py tests/test_voces_propias.py tests/test_i18n_catalogo.py` → 80 passed, 1 failed (la que falla es por `meta_ads`, ver «Trampas»).
- `providers/fal_audio.py`: `"nl": "Dutch"` en `IDIOMAS_MINIMAX` (voces propias, MiniMax) | mismo comando.
- Pruebas actualizadas: `tests/test_audios.py` (tupla de 11 y `test_once_idiomas_con_nombre_y_frase`), `tests/test_fal_audio.py` (conjunto de 11), `tests/test_rutas_audios.py` (el selector pasa a 11 opciones y busca «Nederlands») | **la de rutas no se corrió** (necesita `meta_ads`).
- Skill `audios-y-voces/SKILL.md`: «once idiomas (…, nl; holandés desde 2026-10-07)».
- Rama subida y PR #9 abierto | verificado con: la API de GitHub devolvió `https://github.com/dacolora/iaplusyou/pull/9`; sin checks de CI ni comentarios al 2026-10-07 19:26 UTC.

## Falta, en el orden en que conviene hacerlo
1. Traer la rama y correr la suite completa (en el computador sí está `meta_ads`).
2. Subir a `main` (fast-forward) y desplegar según la skill `despliegue`.
3. Humo y anotar el despliegue.

## La siguiente acción concreta
En una copia de trabajo (worktree, no el checkout principal si tiene trabajo ajeno): `git fetch origin && git checkout audios-holandes && git submodule update --init && git merge origin/main && venv/bin/python3 -m pytest -q`. Si queda verde, `git push origin audios-holandes:main` y seguir la skill `despliegue` desde el paso 3.

Lo que ya se sabe del paso 3: el cambio es solo Python (`audios.py`, `providers/fal_audio.py`), **sin migración**, y `worker.py` importa esos módulos, así que se reinician **los dos servicios** (`iaplusyou` y `creatv-worker`), este último con la cola vacía comprobada en su propio `ssh` y encadenada con `&&` (`deploy/cola_vacia.py`).

## Decisiones ya tomadas (no reabrir)
| Decisión | Respuesta | Quién | Fecha |
|---|---|---|---|
| Agregar el holandés a los idiomas de Audios | Sí, como `nl`, undécimo idioma | Daniel | 2026-10-07 |
| Salir a producción con este cambio | Sí, «sal a pdn» / «ahora sí despliega» | Daniel | 2026-10-07 |
| Motor del holandés | Multilingual v2 como de, fr, it… (no Turbo: Turbo es solo para `no`). Voces propias: MiniMax con `language_boost="Dutch"` | Claude | 2026-10-07 |

## Descartado, y por qué
- Desplegar desde la conversación en la nube — no hay `ssh`, `scp` ni `paramiko` en ese contenedor, no hay `~/.ssh`, y el submódulo privado `meta_ads` no se puede clonar (`could not read Username for 'https://github.com'`). Por eso este relevo.
- Mezclar el PR #9 a `main` desde GitHub sin permiso — es una acción pública y Daniel no lo había autorizado; queda a tu criterio con su visto bueno.
- Comparar con `git stash` el estado anterior de la suite — la guarda `guardas.py` lo frena; usa un commit WIP o un worktree.

## Hechos que no están escritos en otro lado
- `audios.py:35-38,58-69` — las tres estructuras que hay que tocar para un idioma nuevo (`IDIOMAS`, `NOMBRES_IDIOMA`, `FRASES_MUESTRA`); `tests/test_audios.py` exige que sus claves coincidan con `fal_audio.IDIOMAS_MINIMAX`.
- `precalentar_muestras.py` genera de antemano las muestras de las 22 voces; las de holandés se crean la primera vez que alguien las pide (las paga el cliente interno `_creatv`). Opcional correrlo tras desplegar.

## Trampas de esta zona
- En el checkout principal (`/home/user/iaplusyou`) quedaron los **mismos 6 archivos modificados sin commitear** (copias idénticas de lo ya commiteado en la rama; verificado con `git diff --quiet audios-holandes -- <archivo>` → iguales). Hacen saltar el hook de «cambios sin commitear». La guarda impide `git restore` ahí; Daniel puede correr: `git restore .claude/skills/audios-y-voces/SKILL.md audios.py providers/fal_audio.py tests/test_audios.py tests/test_fal_audio.py tests/test_rutas_audios.py`. No los commitees en `main`.
- Sin `meta_ads` falla `tests/test_audios.py::test_el_nombre_del_tipo_locucion_existe_en_el_panel_de_gasto` y no corren las pruebas que importan `dashboard`: con el submódulo inicializado no debería pasar.
- La rama `audios-holandes` está a 1 commit de `origin/main` (`1020e08` al 2026-10-07); si `main` avanzó, haz el merge antes de la suite (ver «Trampas» de la skill `despliegue` sobre submódulo y catálogo tras un merge).

## Plata
- Nada gastado en proveedores. Al desplegar no se cobra nada; las muestras en holandés cuestan solo cuando alguien las pide.

## Estado del árbol
- Commits sin subir: no (rama `audios-holandes` en `bcb5293`, subida) · Pruebas: 80 passed + 1 failed por `meta_ads` en esta sesión; `test_rutas_audios.py` no se corrió y la suite completa tampoco · VPS: no se consultó (sin acceso); el sha que tiene hay que leerlo con `ssh deploy@app.creatvmachine.com 'cd /home/deploy/iaplusyou && git log --oneline -1'`.
