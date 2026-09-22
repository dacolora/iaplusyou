# Generador de propuestas comerciales

El contenido vive en `contenido.json` (una sola fuente). Tres scripts lo
renderizan: `render_doc.py` produce el HTML (sirve para la página web y para
imprimir), `pdf.js` imprime ese HTML a PDF con numeración de páginas y
`render_docx.js` produce el Word. Para una propuesta nueva, copiar la carpeta,
editar el JSON y volver a generar.

Una sola vez, dentro de la carpeta:

```bash
npm init -y && npm install docx@9 puppeteer-core@24
```

Generar:

```bash
python3 render_doc.py      # -> propuesta.html y propuesta_web.html
node pdf.js                # -> propuesta.pdf (usa Google Chrome instalado)
node render_docx.js        # -> propuesta.docx
```

Estructura del JSON: `meta` (datos del membrete, número, fechas, valor),
`carta` (destinatario, asunto, párrafos, firmante) y `secciones`, cada una con
`titulo` y `bloques`. Un bloque puede ser `p`, `sub` (subsección con sus propios
bloques), `lista`, `lista_titulada`, `pasos`, `tabla` (`cols`, `anchos` en %,
`filas`, `numerada`), `precio` (`filas`, `total`, `nota`) o `firmas`. La
numeración 1., 1.1 la calculan los scripts.
