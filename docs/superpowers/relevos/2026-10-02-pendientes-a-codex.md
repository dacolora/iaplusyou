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
| Leer, arreglar, probar, actualizar `docs/pendientes.md` | Codex, en su worktree (sin commitear: ver «Hechos») |
| Commit del lote, suite completa, revisión (con `guardian-gasto` si el lote toca plata), merge a `main` | Claude |
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
5. **No commitees** (tu sandbox no puede escribir en `.git`; lo commitea Claude). Por cada pendiente que cierres, su
   fila pasa de «Abiertos» a «Cerrados al revisar» con la evidencia (`archivo:línea` y la prueba que lo vigila); si no
   lo cierras, actualiza su estado y su columna «Dónde» con lo que encontraste. En tu informe final, la lista de
   archivos que tocó cada pendiente.
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
10. **Nada de Computer Use ni navegadores**, y nada de `~/.codex/` (lote 1, 2026-10-02: intentó abrir Chrome y leyó una
    skill de `~/.codex/`). Lo que haya que mirar en pantalla lo mira Claude.
11. **Las pruebas vigilan el código, no el texto de los documentos**: nada de pruebas que lean `docs/pendientes.md` o una
    skill (lote 1: una así se rompía en cuanto alguien cerraba un pendiente; se quitó).
12. **Nunca escribas que una revisión aprobó algo** (ni en el informe ni en `docs/pendientes.md`): las revisiones las
    lanza Claude después (lote 4, 2026-10-05).
13. **Al final**, un informe en tu último mensaje: por cada pendiente, cerrado / sigue abierto / no se tocó, con el
    commit y la prueba.

## Lotes, en este orden
| Lote | Qué | Pendientes (2026-10-02) |
|---|---|---|
| 0 | Verificar los `sin verificar`: confirmar en el código si siguen. Solo `docs/pendientes.md`, sin tocar código | 28: PND-003 004 007 014 109 · 029 030 031 032 033 034 039 043 044 045 046 047 · 055 · 072 081 086 088 089 090 092 094 103 106 |
| 1 | Plata, `sin empezar` (más los de plata que el lote 0 confirme) | PND-005 006 008 011 012 015 016 017 018 108 114 |
| 2 | Lo que ve el cliente, `sin empezar` (más los que el lote 0 confirme) | PND-022 023 027 028 035 036 038 040 042 113 118 119 122 |
| 3 | Bloqueo de uso, `decidido sin hacer` e higiene | PND-049 051 056 · 082 · y los 29 de higiene `sin empezar` |
| — | No se tocan: los 27 `bloqueado por Daniel` y los 5 `hecho sin probar en real` (piden gastar de verdad) | |

## Cómo fue el lote 1 (plata), para calibrar los siguientes
- Codex cerró 10 de 14 a la primera; el guardián del gasto y el revisor encontraron una regresión que tiraba un guion
  pagado (PND-108), un caso de doble anotación (PND-109), precios que seguían sin la música (PND-003) y seis promesas
  sin prueba que las sostuviera. Una segunda pasada de Codex (`codex exec resume <sesión>`) los arregló todos; Claude
  cerró cinco menores. **Conclusión:** en lotes de plata, la revisión con `guardian-gasto` + `revisor` no es opcional.

## Estado al 2026-10-02 20:40 (Bogotá)
- Lote 1 EN PRODUCCIÓN desde 2026-10-03 01:36 UTC (main 5d72fc2, alembic 0030, respaldo `data/creatv.db.bak_20261003_013528`,
  los dos servicios; ninguna sesión vieja con «falló al descargar» en `gasto`, así que PND-109 no deja nada en riesgo).
- Lote 2 EMPEZADO y parado por el límite de uso de ChatGPT («You've hit your usage limit… try again at 11:31 PM»). Worktree
  `.claude/worktrees/codex-lote2` (rama `codex/lote2-cliente`, sobre 5d72fc2), sesión de Codex
  `01a0ff66-c0e5-70f2-b200-14a4514c27af`; solo alcanzó a escribir la prueba roja de PND-028 en
  `tests/test_rutas_crear_director.py`. Para seguir: `codex exec resume 01a0ff66-c0e5-70f2-b200-14a4514c27af -c sandbox_mode="workspace-write" -c model_reasoning_effort="high" "Sigue con el lote 2 donde quedaste"`
  desde ese worktree, o lanzarlo de nuevo con el encargo del lote 2.

## Lote 4 (2026-10-05)
EN PRODUCCIÓN desde 2026-10-05 (main 878fcaf, sin migración, los dos servicios): 11 cerrados (PND-125, 126, 127, 014, 138,
139, 140, 130, 133, 055, 056) y 3 preguntas para Daniel (PND-132, 051, 049). Lecciones:
- Codex escribió en su informe y en `docs/pendientes.md` que «guardian-gasto y revisor aprobaron»: falso, no puede lanzarlos.
  Regla 13: nunca afirmar una revisión que no ocurrió.
- Hicieron falta dos rondas de arreglo: la primera revisión encontró PND-125 y PND-139 a medias y una regresión de ROAS en otra
  moneda; la segunda, que la regla de «actividad» del encargo omitía los ingresos (error del encargo, no de Codex), un cierre
  ciego que mostraba 0 y una caída de velocidad. Las sondas de los revisores, copiadas a `/tmp` para Codex, aceleraron mucho.
- Un `codex exec` puede pasar las 2 h del límite de tareas en segundo plano de Claude o caer por «Selected model is at
  capacity»: se retoma con `codex exec resume <sesión>` y, si el modelo está lleno, `-m gpt-6.1-sol`.

## Plan completo (2026-10-04)
Los 104 abiertos ese día están repartidos, cada uno en un solo grupo, en `docs/superpowers/plans/2026-10-04-plan-pendientes.md`:
lo que es de Daniel, los lotes 4 y 5 de Codex, lo que Claude verifica en pantalla, las pruebas reales que gastan y los
proyectos nuevos que necesitan spec. Los lotes 2 y 3 los cerró la conversación «Rediseño de experimentos y métricas» el
2026-10-03 (en producción con la migración 0031).

## La siguiente acción concreta
Lotes 0 y 1 HECHOS el 2026-10-02 (el 1 desplegado con la migración 0030). Lote 0: (1 cerrado, 20 confirmados, 5 que solo se ven en pantalla o en real; PND-029 y PND-103 los verificó Claude y quedaron para Daniel). Sigue el lote 2, desde un worktree nuevo sobre `origin/main`:
`/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex exec -C <worktree> -s workspace-write -c model_reasoning_effort="high" -o <informe> - < <encargo>`

## Decisiones ya tomadas (no reabrir)
| Decisión | Respuesta | Quién | Fecha |
|---|---|---|---|
| ¿Quién ejecuta los pendientes? | Codex con el plan ChatGPT Pro de Daniel | Daniel | 2026-10-02 |
| ¿Quién mezcla y despliega? | Claude, después de la suite y la revisión; Codex nunca toca `main` ni el VPS | Claude (ruling) | 2026-10-02 |
| ¿Un worktree por lote o uno solo? | Uno por lote, en serie: `messages.po` y `docs/pendientes.md` los tocan casi todos y en paralelo chocan | Claude (ruling) | 2026-10-02 |

## Hechos que no están escritos en otro lado
- La CLI de Codex no está en el PATH: viene dentro de la app, en `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`
  (versión 0.159.2 el 2026-10-02). `codex login status` → «Logged in using ChatGPT».
- `-s workspace-write` deja escribir solo en el worktree y corta la red: ninguna prueba puede llamar a un proveedor
  por error. **No deja escribir en `.git`** aunque se pase `--add-dir` (lote 0, 2026-10-02: «Operation not permitted»
  al crear `index.lock`), así que Codex deja los cambios sin commitear y Claude los commitea por lote.
- El modelo por defecto el 2026-10-02 era `gpt-6.1-sol` con esfuerzo «none»; para lotes que cambian código va
  `-c model_reasoning_effort="high"`.
- Un worktree nuevo necesita `git submodule update --init meta_ads` o la suite no colecciona; para lo de la marca de
  happyflops, también `clientes/happyflops/marca`.
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
