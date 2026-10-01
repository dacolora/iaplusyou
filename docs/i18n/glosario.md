# Glosario de traducción (español → inglés)

Fuente: spec `docs/superpowers/specs/2026-09-26-idioma-y-modo-oscuro-design.md` §B10, punto de
partida a revisar por Daniel. Lo usa quien traduzca `translations/en/LC_MESSAGES/messages.po`
(`catalogo_i18n.py actualizar` / `pendientes` / `compilar`).

## Términos

| Español | Inglés |
|---|---|
| Proyecto | Project |
| Crear | Create |
| Tablero | Dashboard |
| Catálogo | Catalog |
| Experimentos | Experiments |
| Sprints | Sprints |
| Nicho | Niche |
| Avatar / sub-avatar | Avatar / sub-avatar |
| Referentes | Swipe file |
| Barrido | Sweep |
| Configuración | Settings |
| Puesta a punto | Setup |
| Conexiones | Connections |
| Gasto | Spend |
| Pieza | Piece |
| Final (final edition) | Final cut |
| Destino | Market |
| Guion | Script |
| Gancho | Hook |
| Ángulo | Angle |
| Consciencia | Awareness |
| Aprobar / Rechazar | Approve / Reject |
| Pauta (gasto en Meta) | Ad spend |
| Publicación orgánica | Organic post |
| Mi música | My music |
| Flow Plus | Flow Plus |
| Campaña | Campaign |
| Persona (arquetipo) | Persona |
| Referente (un anuncio) | Reference |
| Familia de formato | Format family |
| Firma («por qué funciona») | Why it works |
| Dolor | Pain point |
| Momento del mes | Moment of the month |
| Temporada | Season |
| Idea | Idea |
| Lote | Batch |
| Entrega | Delivery |
| Estudio (Nicho) | Study |
| Núcleo (de deseo) | Core |
| Comentario | Comment |
| Investigación | Research |
| Arranque (lead) | Lead |
| Sofisticación | Sophistication |
| Prueba (de un producto) | Proof |
| Final edition (la pestaña) | Final edition |
| Guion base | Base script |
| Localizar | Localize |
| Variante | Variant |
| Capa | Layer |
| Mezcla | Mix |
| Sonido de la escena | Scene sound |
| Edición (del editor) | Edit |
| Vista previa | Preview |
| Línea de tiempo | Timeline |
| Pista | Track |
| Cabezal | Playhead |
| Cortar (en el cabezal) | Split |
| Recortar | Trim |
| Tramo (del render) | Segment |
| Copia liviana (proxy) | Lightweight copy |
| Producir | Produce |
| Biblioteca (del editor) | Library |
| Medios | Media |
| Transición | Transition |
| Corte (transición) | Cut |
| Fundido | Fade |
| Fundido a negro | Fade to black |
| Deslizar | Slide |
| Zoom lento | Slow zoom |
| Llamado (texto de muestra) | Call to action |
| Contorno | Outline |
| Sombra | Shadow |
| Fondo (de un texto) | Background |
| Subir (un archivo) | Upload |
| Editar (el panel) | Edit |
| Fuente (tipografía del editor, `msgctxt "editor"`) | Font |

## Reglas de estilo

- Tuteo (español informal, "vos"/"tú") → "you" en inglés (sin formalidad artificial).
- Mayúscula solo al inicio de la frase, igual que el español (nunca Title Case en inglés).
- Emojis, `·` y marcadores `%(x)s` quedan intactos — se copian tal cual, nunca se traducen ni se
  reordenan.
- Los marcadores `{n}`, `{mensaje}`… de los textos del editor (`final_edition/textos_editor.py`) se
  copian intactos, igual que `%(x)s`.
- Las etiquetas HTML dentro de una frase quedan intactas y en el mismo lugar relativo (la frase
  completa es un solo `msgid`, nunca partida en varios).
- Comillas: « » y las rectas `" "` en español se convierten a comillas curvas `“ ”` en el `msgstr`
  en inglés.
- `%` literal (no parte de un marcador `%(x)s`) se escribe `%%` en plantillas (Jinja "newstyle"
  aplica `%` a todo el texto, haya o no marcador) y en una llamada de Python que pasa variables
  (`gettext("...%%...", x=...)`, mismo motivo). En una llamada de Python SIN variables
  (`gettext("100% listo")`) no hay interpolación de por medio: ahí un `%` literal va suelto, tal
  cual — duplicarlo mostraría los dos signos.
- Números: la coma decimal del español pasa a punto en inglés y el separador de miles a coma
  (`0,028` → `0.028`; `1.234.567` → `1,234,567`) — cambia solo el separador, nunca el valor ni el
  símbolo de moneda (ver «No se traduce»).

## No se traduce

- Nombres de marca y de modelos: Creatv, Flow Plus, Wan, Kling, Seedance, Seedream, WaveSpeed, Meta,
  Shopify, y cualquier otro nombre propio de proveedor o producto.
- Códigos: TOF, MOF, BOF y cualquier otra sigla/clave interna.
- Unidades: `s` (segundos), `US$` y cualquier símbolo de moneda.
