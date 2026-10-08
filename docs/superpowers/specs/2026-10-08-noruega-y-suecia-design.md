# Noruega y Suecia en Creatv (spec 2026-10-08)

## 1. Por qué

Daniel, 2026-10-08: «necesitamos Noruega o Suecia en nuestra máquina, muy importante, porque este es casi que el público
objetivo de happyflops». Hoy Creatv solo conoce ocho países (`final_edition.tipos.PAISES`: CO, MX, US, ES, BR, AR, CL,
PE) y las finales solo salen en español, inglés y portugués (`dashboard.IDIOMAS_FE`). Por eso no se puede producir una
final en noruego o sueco, ni lanzar un experimento con un conjunto en Noruega o Suecia, ni planear un sprint con el
calendario de esos países. Triple Whale ya acepta tiendas de cualquier país desde el spec 2026-10-08 de varias tiendas
(PND-147 nació ahí).

Decisión: entran **Noruega (NO, noruego bokmål, NOK)** y **Suecia (SE, sueco, SEK)**, de punta a punta. La forma del
cambio deja que otro país europeo sea una fila más. La interfaz de Creatv sigue en español e inglés: lo que cambia es
el idioma de lo que se publica.

## 2. Qué cambia para la persona

- En Final edition, «Destinos» ofrece Noruega y Suecia; la final sale con guion, voz, subtítulos y texto en pantalla en
  noruego o sueco, y el precio en coronas («299 kr», «1 299 kr»).
- En «Nuevo experimento», Noruega y Suecia aparecen entre los países, con el presupuesto mínimo correcto si la cuenta
  de Meta factura en NOK o SEK.
- En Sprints, el país del proyecto puede ser Noruega o Suecia, con su calendario comercial; las ideas se pueden pedir
  en noruego o sueco.
- En Nicho, los estudios aceptan Noruega (Suecia ya estaba) y los avatares en noruego.
- Triple Whale permite cifras en NOK o SEK.

## 3. Países y monedas

- `final_edition/tipos.PAISES` gana:
  - `"NO": {"nombre": N_("Noruega"), "idioma": "no", "moneda": "NOK", "simbolo": "kr", "bandera": "🇳🇴"}`
  - `"SE": {"nombre": N_("Suecia"), "idioma": "sv", "moneda": "SEK", "simbolo": "kr", "bandera": "🇸🇪"}`
  El código de idioma noruego es `"no"`, el mismo que ya usan `audios.IDIOMAS` y `providers/fal_audio.IDIOMAS_MINIMAX`.
- `formatear_precio` para NO y SE: miles con espacio, sin decimales si el valor es entero y con coma decimal si no,
  símbolo detrás con espacio: `299 kr`, `1 299 kr`, `149,50 kr`.
- `presupuesto_experimentos.PRESUPUESTO_MINIMO_DIARIO`: `"NOK": 10, "SEK": 10` (Meta pide el equivalente a ~1 USD al
  día). `lanzador._MIN_POR_MONEDA`: `"NOK": 1000.0, "SEK": 1000.0` (el equivalente al de EUR/USD). La regla de que se
  compara contra la moneda de FACTURACIÓN de la cuenta no cambia.
- `triple_whale.MONEDAS` gana `"NOK"` y `"SEK"`.
- `proyectos.PAISES_CALENDARIO` deja de ser una copia: sale de `tipos.PAISES` (mismo orden), así NO y SE entran solos.
- `nicho/datos.PAISES_ESTUDIO` y `NOMBRES_PAIS` ganan NO (SE ya está).

## 4. Idiomas de lo que se publica

Un solo lugar nuevo con los nombres de los idiomas de publicación, para no repetir diccionarios:
`idiomas_publicacion.py` (sin Flask en el import) con
`NOMBRES = {"es": "español", "en": "inglés", "pt": "portugués", "sv": "sueco", "no": "noruego (bokmål)"}`
y `NOMBRES_EN = {"es": "Spanish", "en": "English", "pt": "Portuguese", "sv": "Swedish", "no": "Norwegian (Bokmål)"}`,
más `nombre(codigo, en_ingles=False)`. Los diccionarios que ya existen en otros módulos para su propio propósito
(audios, nicho, sprints) se amplían con sv/no donde falte, sin fusionarlos (fuera de alcance).

- `dashboard.IDIOMAS_FE` = `("es", "en", "pt", "sv", "no")`. El formulario de destinos (`_destinos_form`) y
  `fe_producir` aceptan las combinaciones idioma_país de `PAISES`.
- **Prompts de Claude** (`final_edition/guion.py`, `_system_localizar` y `_mensaje_localizar`): además del código, el
  idioma va por su nombre («noruego (bokmål)», «sueco»). Con el código solo, `'no'` se lee como la palabra «no». Mismo
  arreglo en cualquier prompt que hoy ponga el código de idioma suelto para escribir copy publicable (revisar
  `guion.py`, `sprints/ideas.py`, `organico.py`, `generador_prompts.py`).
- **Voz** (`providers/fal_audio.VOCES`, la voz de las finales): entradas para `"sv"` y `"no"` con las mismas voces
  multilingües que ya usa `"pt"`; para `"no"` se fuerza el modelo Turbo con `language_code`, como ya hace `audios`
  (`IDIOMAS_TURBO`). Las voces propias ya aceptan sv/no.
- **Subtítulos y transcripción**: Whisper recibe el idioma; se comprueba que sv/no llegan tal cual.
- **Texto en pantalla**: las 11 fuentes de `static/fonts/` traen å ä ö ø æ (comprobado con fontTools el 2026-10-08).
  Se comprueba que la tabla de cobertura del render v1 (`final_edition/tipografia.py`, `sin_glifos_v1`) no quita esas
  letras; si las quita, se amplía la tabla.
- **Publicación orgánica y prompts de imagen**: `organico.py` (link en bio, CTA, «escríbenos») y
  `generador_prompts.LINK_EN_BIO` ganan sv y no, en ese idioma: «Lenke i bio» / «Länk i bion», etc.
- **Sprints**: `sprints/datos.IDIOMAS` y `IDIOMAS_NOMBRE` ganan sv y no.
- **Nicho**: `nicho/avatares.IDIOMAS` y `nicho/investigacion._NOMBRE_IDIOMA` ganan no.

## 5. Calendario comercial (Sprints)

`sprints/calendario.PRESETS` gana NO y SE (hoy un país sin calendario cae al de Colombia, con el Día de la madre en
mayo). Fechas como ventanas de venta del año, igual que los demás:

- **NO**: Valentinsdagen (02-01 a 02-14), Morsdag (segundo domingo de febrero: ventana 01-28 a 02-12), 17. mai
  (05-05 a 05-17), Fellesferie/verano (06-20 a 07-31), Farsdag (segundo domingo de noviembre: 10-28 a 11-12),
  Black Friday, Jul (11-15 a 12-24).
- **SE**: Alla hjärtans dag (02-01 a 02-14), Mors dag (último domingo de mayo: 05-15 a 05-31), Midsommar (06-10 a
  06-24), verano/semester (06-20 a 07-31), Fars dag (segundo domingo de noviembre: 10-28 a 11-12), Black Friday, Jul
  (11-15 a 12-24).
Cada temporada con su `contexto` y `mood_visual` (textos con `N_`), como las de los otros países.

## 6. Textos

Todo texto nuevo visible (nombres de país, temporadas) pasa por el catálogo (regla 3): `N_`/`_()`, luego
`catalogo_i18n.py actualizar`, traducción al inglés con `docs/i18n/glosario.md` y `compilar`. Los textos publicables
en noruego/sueco (link en bio, CTA) NO pasan por el catálogo: son contenido por idioma de publicación, como los de pt.

## 7. Pruebas

- `formatear_precio` NO/SE (entero, con miles, con decimales).
- Destinos: `no_NO` y `sv_SE` válidos en el formulario de Final edition; `sv_NO` también (es una combinación válida
  de idioma y país) y `xx_NO` no.
- `_system_localizar("no", "NO")` contiene «noruego (bokmål)» y la moneda NOK.
- Voz: `VOCES["no"]` y `VOCES["sv"]` existen; una voz en noruego pide Turbo con `language_code="no"` (doble del
  proveedor, sin cobrar).
- Experimento: `exp_probar` acepta NO y SE; presupuesto mínimo NOK/SEK; el conjunto de Meta lleva
  `geo_locations.countries=["NO"]`.
- `proyectos.guardar_pais("acme", "NO")` vale; el calendario de NO trae Morsdag en febrero.
- Orgánico y generador: link en bio en sv/no.
- Tipografía v1: «Kjøp nå – spar 20 %» y «Köp nu – Åre» no pierden letras.
- Suite completa verde, con lentas.

## 8. Prueba real (centavos)

Después de desplegar, con la llave de producción y sin tocar los datos de ningún proyecto: localizar un guion corto
de prueba a `no`/NO y a `sv`/SE con `guion.localizar_guion` (Claude, centavos) y generar 5 s de voz en noruego con la
voz de las finales (fal, centavos), registrando el gasto en el proyecto interno de Creatv. Se mira que el texto esté
en el idioma correcto y que el precio salga en coronas.

## 9. Fuera de este cambio

- Más países europeos (Dinamarca, Finlandia, Alemania…): una fila en `PAISES` y su calendario cuando Daniel los pida.
- La interfaz de Creatv en noruego o sueco.
- Unificar los diccionarios de nombres de idioma repartidos por módulos.
