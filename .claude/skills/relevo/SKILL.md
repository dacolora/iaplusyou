---
name: relevo
description: "Relevo (handoff) entre conversaciones: escribe docs/superpowers/relevos/AAAA-MM-DD-<tema>.md para que otra conversación (o Codex) siga el trabajo sin leer este chat, con lo hecho y cómo se verificó, lo descartado y por qué, y la siguiente acción concreta. Cargar antes de cortar un trabajo a medias, cuando el contexto se esté llenando, o cuando Daniel diga que otra conversación sigue con esto."
---

# Relevo entre conversaciones

En este repo trabajan varias conversaciones a la vez y ninguna ve el chat de otra. Un resumen automático pierde
justo lo que más cuesta volver a descubrir: qué camino ya se descartó, qué prueba ya se corrió, qué supuesto resultó
falso. Este archivo lo guarda.

**La prueba que tiene que pasar:** alguien que no estuvo aquí lee `CLAUDE.md` y este archivo, y puede dar el siguiente
paso **sin preguntar nada que ya se respondió**. Si tendría que repetir una búsqueda que ya hiciste, no está terminado.

## Dónde y cómo

`docs/superpowers/relevos/AAAA-MM-DD-<tema>.md` (fecha absoluta, tema en minúsculas con guiones), commiteado en la
rama del trabajo, y su ruta en tu último mensaje a Daniel.

```markdown
# Relevo — <tema>
**Escrito:** AAAA-MM-DD HH:MM (hora de Bogotá) · **Rama / worktree:** <nombre> · **Spec o plan:** <ruta o «ninguno»>

## En un párrafo
<qué es el trabajo y hasta dónde llegó, en llano>

## Hecho, y cómo se verificó
- <qué> | verificado con: <comando exacto y su resultado, p. ej. «pytest tests/test_x.py -q → 12 passed»>

## Falta, en el orden en que conviene hacerlo
- <…>

## La siguiente acción concreta
<una sola: el archivo, la función, el comando>

## Decisiones ya tomadas (no reabrir)
| Decisión | Respuesta | Quién | Fecha |

## Descartado, y por qué
- <camino probado o pensado> — se descartó porque <motivo, con archivo:línea si fue código>

## Hechos que no están escritos en otro lado
- <archivo:línea> — <lo que costó averiguar>

## Trampas de esta zona
- <lo que le va a morder al siguiente, con evidencia>

## Plata
- <lo gastado en proveedores durante el trabajo y lo que falta gastar, o «nada»>

## Estado del árbol
- Commits sin subir: <sí/no, cuáles> · Pruebas: <conteo exacto o «no se corrieron»> · VPS: <qué sha tiene, si aplica>
```

## Reglas

- Fechas absolutas, nunca «ayer» ni «la sesión pasada».
- Cada «hecho» dice cómo se verificó. «Arreglé el bug» no es un estado; «arreglado en `tareas/flowplus.py:412`,
  verificado con `pytest tests/test_flowplus.py -q` → 48 passed» sí.
- Lo descartado se anota siempre: es lo único que la siguiente conversación no puede reconstruir y va a repetir.
- Si las pruebas no corrieron, se escribe «no se corrieron». Nunca se presenta como terminado algo sin probar.
- Lo que ya es regla del repo no va aquí: va a la skill de su área en el mismo cambio.
