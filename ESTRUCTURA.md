# Mapa del repositorio

Este documento existe para que cualquiera —vos mismo repasando, un socio, alguien
nuevo en el proyecto— pueda ubicar rápido dónde vive cada cosa sin tener que
adivinar. Está organizado por lo que cada carpeta/archivo *hace* en el flujo,
no alfabéticamente.

Generado el 1 sep 2026 a partir del estado real del repo — si la estructura
cambia mucho, vale la pena regenerarlo en vez de confiar en que sigue exacto.

## El flujo completo, en una línea

```
IDEA (texto) → PROMPTS/CONCEPTOS (texto) → IMAGEN → VIDEO → PUBLICACIÓN
     ↑                                        ↑         ↑
  generador_prompts.py                 providers/    publicador.py
```

Cada flecha es una aprobación humana obligatoria — nunca se salta un paso solo
(ver CLAUDE.md, sección "Qué es esto").

## 1. El corazón: la app web

```
dashboard.py          ← TODO pasa por acá. Rutas Flask, sube archivos, lanza
                         jobs en background, arma qué le manda a cada template.
templates/
  base.html            ← esqueleto de toda página + JS de polling de progreso
  cliente.html         ← la página de un proyecto (tabs)
  _tab_nueva_idea.html    → tab "Nueva idea" (genera imagen+video desde texto)
  _tab_cambiar_calzado.html → tab "Cambiar calzado" (swap sobre foto/video real)
  _tab_settings.html      → tab "Settings" (identidad de marca)
  _idea_card.html, _idea_visual_card.html, _prompt_row.html,
  _imagen_row.html, _video_card.html, _progreso_row.html,
  _comparacion_modelos.html  ← piezas reusables dentro de esos tabs
static/style.css      ← todo el CSS, un solo archivo
```

## 2. La "memoria": módulos que leen/escriben JSON (sin base de datos)

Cada uno es dueño de UN archivo de estado por cliente:

| Módulo Python | Archivo que administra | Qué guarda |
|---|---|---|
| `estado.py` | `estado_videos.json` | videos generados, camino a aprobación final/publicación |
| `prompts.py` | `prompts_pendientes.json` | flujo viejo: idea → 5 prompts de texto → imagen → video |
| `conceptos_imagen.py` | `conceptos_pendientes.json` | flujo nuevo "imagen primero": idea → N imágenes → animaciones |
| `swaps.py` | `swaps.json` | resultados de "cambiar calzado" |
| `marca.py` | `clientes/<c>/marca/root.json` | identidad de marca (reglas, invariantes) |
| `catalogo_productos.py` | *(no JSON, lee carpetas)* | lista los productos desde `clientes/<c>/productos/` |
| `bitacora.py` | `registro_generaciones.csv` | log plano de qué se generó, cuándo, con qué costo |
| `trabajos.py` | *(en memoria, no archivo)* | jobs en background + guardado anti-doble-click |

## 3. Los proveedores de IA — `providers/`

Esta es la capa que le habla a cada API externa. La regla: el resto del código
nunca dice "Higgsfield" o "Nano Banana" directo — le pide a esta capa
"generame una imagen/video" y ella decide.

```
providers/
  image_provider.py       ← capa única para imagen (Higgsfield | Nano Banana)
  video_provider.py       ← capa única para video (Higgsfield | Seedance)
  nano_banana_client.py   ← Gemini 2.5 Flash Image, directo
  seedance_client.py      ← Seedance 2.0, vía fal.ai
  kling_o1_client.py      ← Kling O1 (edición de video real), vía fal.ai
  wavespeed_client.py     ← Wan 2.7 Video Edit, vía WaveSpeed AI
  comparador_modelos.py   ← Luma Ray3, Wan-2.2 Animate Replace, Qwen Edit,
                             Nano Banana vía fal — todos vía fal.ai
  fal_client.py           ← helper HTTP compartido para todo lo de fal.ai
  aspect_ratio.py         ← detecta proporción de una foto/video subido
```

Fuera de `providers/`: `higgsfield_client.py` (en la raíz, es el original —
Higgsfield sigue siendo el default de video en el flujo principal).

`generador_prompts.py` es aparte: no genera imagen ni video, genera *texto*
(los prompts, las descripciones de escena) llamando a Anthropic directo.

## 4. Multi-cliente — `clientes/<nombre>/`

Cada proyecto/marca es una carpeta. Hoy solo existe `happyflops`:

```
clientes/happyflops/
  marca/            ← identidad de marca real (root.json, schema.json — SÍ se versiona en git)
  personajes/       ← fotos/videos de referencia del personaje
  productos/         ← catálogo de calzado (una subcarpeta = un producto/color)
    ho_rose/, ho_sky/, horiginal/
  briefs/            ← briefs de publicación (qué video, a qué plataformas)
  *.json             ← los archivos de estado de la tabla de arriba (NO se versionan)
```

## 5. Publicación

```
publicador.py          ← decide a qué plataformas publicar un video, según el brief
uploaders/
  youtube_uploader.py, meta_uploader.py (FB+IG), tiktok_uploader.py
auth/
  auth_youtube.py, auth_meta.py, auth_tiktok.py  ← login OAuth, se corre UNA VEZ
                                                     a mano, local (no en servidor)
```

## 6. Storage

```
storage/r2_uploader.py  ← sube cualquier binario generado a Cloudflare R2
                            (todo lo generado vive ahí, nunca en git)
```

## 7. Scripts sueltos (anteriores al dashboard, siguen funcionando)

```
run_batch.py        ← corre un lote de briefs sin abrir el navegador
revisar.py           ← revisa/aprueba desde terminal
subir_personaje.py    ← sube referencias de personaje desde terminal
validar_marca.py      ← valida un submundo.schema.json de la matriz de marca
```

## 8. Documentación

```
CLAUDE.md             ← la "biblia" técnica del repo, para trabajar con Claude Code
ROADMAP.md             ← comparación de proveedores con precios reales, para
                          explicarle a un socio/inversionista en español llano
SETUP.md               ← guía paso a paso para configurar todo desde cero
ESTRUCTURA.md           ← este archivo
docs/agents/            ← config de flujo de trabajo con Claude (issue tracker, etc.)
docs/superpowers/specs/ ← diseños técnicos escritos antes de construir features grandes
```

## 9. Cosas sueltas que probablemente valga la pena ordenar

- `HO-rose/`, `HO-sky/`, `HOriginal/` en la **raíz** del repo — parecen las
  fotos originales de producto antes de organizarse dentro de
  `clientes/happyflops/productos/`. Están duplicadas ahí y en `clientes/`.
- `briefs_example.json` en la raíz — ejemplo suelto, no parte de ningún cliente.
