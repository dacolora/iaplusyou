# Relevo — los pendientes de `docs/pendientes.md` pasan a Codex (ChatGPT)
**Escrito:** 2026-10-02 18:30 (hora de Bogotá) · **Rama / worktree:** un worktree por lote, `.claude/worktrees/codex-<lote>` · **Spec o plan:** `docs/pendientes.md` (el registro único)

## En un párrafo
Daniel decidió el 2026-10-02 que los pendientes abiertos de `docs/pendientes.md` (117 ese día) los ejecute Codex con su
plan ChatGPT Pro, para que el gasto salga de ese plan. Claude Code orquesta: arma cada lote, lanza `codex exec` en un
worktree propio, revisa lo que vuelve, lo mezcla a `main` y lo despliega con la skill `despliegue`. Codex implementa,
prueba y commitea en su rama, y nada más.

## Quién hace qué
| Paso | Quién |
|---|---|
| Elegir el lote y escribir su encargo | Claude |
| Leer, arreglar, probar, commitear, actualizar `docs/pendientes.md` | Codex, en su worktree |
| Suite completa, revisión (con `guardian-gasto` si el lote toca plata), merge a `main` | Claude |
| Desplegar (respaldo, migración, cola vacía, reinicio) | Claude, con la skill `despliegue` |
| Lo `bloqueado por Daniel` (llaves, pagos, decisiones, clics en Meta) | Daniel |

## Reglas para Codex
Los hooks de `.claude/` (`guardas.py`, `verificar_edicion.py`) **no corren en Codex**: estas reglas las cumple Codex
por su cuenta. Además valen todas las de `AGENTS.md` (enlace a `CLAUDE.md`) y la skill del área que toques
(`.claude/skills/<área>/SKILL.md`; la tabla «Qué skill cargar» dice cuál).

1. **Solo en tu worktree.** Nunca escribas en el checkout principal `/Users/colorado/Documents/GitHub/iaplusyou`: ahí
   otras conversaciones tienen trabajo sin commitear (2026-09-27, un merge a medias de otra conversación).
2. **Nada de llaves.** No leas ni imprimas `.env`, `data/`, `usuarios.json`, `clientes/*/meta*.json`,
   `clientes/*/token_*.json` ni nada de `~/.codex/`. Lo que imprimes queda en el historial de ChatGPT.
3. **Nada que cobre ni publique.** No llames a ningún proveedor real (Anthropic, WaveSpeed, fal, Apify, Atria, Meta,
   TikTok, Shopify…); las pruebas usan dobles, como el resto de la suite. Si un pendiente solo se cierra con una
   prueba real que gasta, déjalo `hecho sin probar en real` y anota qué prueba falta.
4. **Git:** `git add <rutas>` explícitas; nunca `git add -A`, `git stash`, `git reset --hard`, `git checkout .`,
   `push`, `merge` ni `rebase`. Nunca `ssh` al VPS.
5. **Un commit por pendiente**, mensaje en español: `PND-NNN: <qué cambió>`. En el mismo commit, su fila pasa de
   «Abiertos» a «Cerrados al revisar» con la evidencia (`archivo:línea` y la prueba que lo vigila). Si no lo cierras,
   actualiza su estado y su columna «Dónde» con lo que encontraste.
6. **Pruebas:** el venv es el del checkout principal:
   `/Users/colorado/Documents/GitHub/iaplusyou/venv/bin/python3 -m pytest <archivos> -q -p no:cacheprovider`. Cada
   arreglo lleva una prueba que falla sin él. Al terminar el lote, la suite completa (unos 5 minutos, 5 781 pruebas
   el 2026-10-02).
7. **Texto visible:** por el catálogo (regla 3 de `CLAUDE.md`):
   `venv/bin/python3 catalogo_i18n.py actualizar`, traducir con `docs/i18n/glosario.md`, `compilar`, sin `fuzzy`.
8. **Dos intentos por pendiente.** Si a la segunda no sale, déjalo, anota qué probaste y sigue con el siguiente
   (regla «Cómo se trabaja» 1).
9. **No decidas por Daniel.** Lo `bloqueado por Daniel`, lo que pida rediseñar (otro flujo, otro proveedor, otra
   frontera entre módulos) y lo que cambie cómo se cobra o qué se publica: no lo hagas; anótalo como pregunta en la
   fila.
10. **Al final**, un informe en tu último mensaje: por cada pendiente, cerrado / sigue abierto / no se tocó, con el
    commit y la prueba.

## Lotes, en este orden
| Lote | Qué | Pendientes (2026-10-02) |
|---|---|---|
| 0 | Verificar los `sin verificar`: confirmar en el código si siguen. Solo `docs/pendientes.md`, sin tocar código | 28: PND-003 004 007 014 109 · 029 030 031 032 033 034 039 043 044 045 046 047 · 055 · 072 081 086 088 089 090 092 094 103 106 |
| 1 | Plata, `sin empezar` (más los de plata que el lote 0 confirme) | PND-005 006 008 011 012 015 016 017 018 108 114 |
| 2 | Lo que ve el cliente, `sin empezar` (más los que el lote 0 confirme) | PND-022 023 027 028 035 036 038 040 042 113 118 119 122 |
| 3 | Bloqueo de uso, `decidido sin hacer` e higiene | PND-049 051 056 · 082 · y los 29 de higiene `sin empezar` |
| — | No se tocan: los 27 `bloqueado por Daniel` y los 5 `hecho sin probar en real` (piden gastar de verdad) | |

## La siguiente acción concreta
Lanzar el lote 0 (Claude), desde un worktree nuevo sobre `origin/main`:
`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex exec -C <worktree> -s workspace-write --add-dir /Users/colorado/Documents/GitHub/iaplusyou/.git -o <informe> - < <encargo>`

## Decisiones ya tomadas (no reabrir)
| Decisión | Respuesta | Quién | Fecha |
|---|---|---|---|
| ¿Quién ejecuta los pendientes? | Codex con el plan ChatGPT Pro de Daniel | Daniel | 2026-10-02 |
| ¿Quién mezcla y despliega? | Claude, después de la suite y la revisión; Codex nunca toca `main` ni el VPS | Claude (ruling) | 2026-10-02 |
| ¿Un worktree por lote o uno solo? | Uno por lote, en serie: `messages.po` y `docs/pendientes.md` los tocan casi todos y en paralelo chocan | Claude (ruling) | 2026-10-02 |

## Hechos que no están escritos en otro lado
- La CLI de Codex no está en el PATH: viene dentro de la app, en `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`
  (versión 0.159.2 el 2026-10-02). `codex login status` → «Logged in using ChatGPT».
- `-s workspace-write` deja escribir solo en el worktree; un commit de un worktree escribe en `.git` del checkout
  principal, por eso va `--add-dir /Users/colorado/Documents/GitHub/iaplusyou/.git`. Ese sandbox corta la red: así
  ninguna prueba puede llamar a un proveedor por error.
- Un worktree nuevo necesita `git submodule update --init meta_ads` o la suite no colecciona.
- Las pruebas no hacen red.

## Trampas de esta zona
- **Varios lotes en paralelo** pisan `translations/en/LC_MESSAGES/messages.po` y `docs/pendientes.md`. Se corren en
  serie, y si `main` avanzó se mezcla antes de empezar el siguiente. El catálogo se rellena leyendo el `.po` completo
  con Babel, nunca a partir de un diff (2026-09-30).
- **IDs de pendientes:** otra conversación puede tomar números nuevos mientras corre un lote. El siguiente ID libre se
  mira justo antes de commitear.

## Plata
- Ninguna en proveedores. Codex gasta del plan ChatGPT Pro de Daniel.

## Estado del árbol
- `main` = fdbbaf5 (Alertas desplegado 2026-10-02 22:48 UTC, alembic 0029). Pruebas: 5 781 passed, 1 skipped. VPS en fdbbaf5.
