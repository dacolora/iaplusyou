# 0004. Doctrina destilada y ángulo en los `extra`

Fecha: 2026-09-25. Estado: aceptado.

Daniel pidió que seis libros de copywriting (Kennedy, Hopkins, Ogilvy, Great Leads, Schwartz, Theriot) fueran «la
base que alimenta toda la generación de contenido». La app llamaba a Claude en 23 sitios, cada uno con su prompt
escrito a mano y sin ningún criterio común sobre qué decir.

**Decisión:** los principios se destilan en nuestras palabras en `doctrina/textos/*.md`, partidos en rebanadas por
etapa, y cada llamada recibe solo la suya como system prompt con caché. Antes de escribir, Claude decide un **ángulo**
que se guarda en los `extra` JSON que ya existen (`campana_pieza`, `concepto`, `pieza.capas`, `referente`, `persona`)
y viaja de la idea al video, al guion y al caption. Toda cifra que Claude escriba se verifica contra los datos que
recibió.

## Alternativas descartadas

- **RAG sobre los libros**: un buscador por similitud no encuentra el principio correcto a partir de una ficha de
  producto; pegar pasajes literales diluye las instrucciones, cuesta más por llamada y reproduce texto con derechos.
- **Los libros en el repo o en el servidor**: cuatro tienen derechos de autor, y la app no los necesita: le basta
  la doctrina destilada.
- **Campos nuevos con migración**: el bloque 1 no muestra nada; los `extra` alcanzan y `duplicar` ya copia
  `concepto.extra`. El bloque 2 decidirá qué campos se vuelven columnas editables.

## Consecuencias

- Cada llamada lleva 1–3 mil tokens más de entrada (menos con caché en lotes).
- Un guion con una cifra que no está en los datos no se guarda: va a corrección y, si persiste, falla.
- Localizar no verifica cifras: convierte unidades y precios, y el guion base ya se verificó al escribirse.
