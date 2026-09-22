import html, json, os
H = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(H, "contenido.json")))
M = D["meta"]; e = html.escape

CSS = """
:root{ --ground:#e9ecf1; --ground-text:#4b5566; }
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){ --ground:#111318; --ground-text:#9aa3b2; } }
:root[data-theme="dark"]{ --ground:#111318; --ground-text:#9aa3b2; }
html{font-size:16px}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:#1c2230;font-family:"Source Sans 3","Helvetica Neue",Arial,sans-serif;line-height:1.5;-webkit-font-smoothing:antialiased}
.hoja{max-width:8.5in;margin:0 auto;padding:.9in .95in 1in;background:#fff;color:#1c2230;box-shadow:0 2px 24px rgba(20,30,50,.12)}
.marco{padding:32px 16px 48px}
h1,h2,h3{margin:0;color:#1b2a41;text-wrap:balance}
h1{font-family:"Source Serif 4",Georgia,"Times New Roman",serif;font-weight:600;font-size:1.65rem;line-height:1.25}
h2{font-family:"Source Serif 4",Georgia,"Times New Roman",serif;font-weight:600;font-size:1.25rem;line-height:1.3;margin:2rem 0 .8rem;padding-bottom:.35rem;border-bottom:1px solid #1b2a41;break-after:avoid}
h2 .n{display:inline-block;min-width:1.7rem}
h3{font-size:1rem;font-weight:600;margin:1.3rem 0 .5rem;break-after:avoid}
h3 .n{display:inline-block;min-width:2.2rem;color:#5f6b7d;font-variant-numeric:tabular-nums}
p{margin:0 0 .7rem;text-align:justify;hyphens:auto}
.eyebrow{font-size:.72rem;font-weight:600;letter-spacing:.14em;text-transform:uppercase;color:#5f6b7d}
.muted{color:#5f6b7d}
.small{font-size:.85rem}

.membrete{display:flex;justify-content:space-between;align-items:flex-end;gap:2rem;padding-bottom:.7rem;border-bottom:2px solid #1b2a41}
.marca{font-family:"Source Serif 4",Georgia,serif;font-size:1.45rem;font-weight:600;color:#1b2a41;line-height:1.1}
.marca b{font-weight:600;color:#3f6fb8}
.marca + .eyebrow{margin-top:.35rem}
.emp{text-align:right;font-size:.78rem;line-height:1.45;color:#5f6b7d}
.emp b{color:#1c2230;font-weight:600}

.titulo{margin:2.2rem 0 1.6rem}
.titulo .eyebrow{margin-bottom:.6rem}
.titulo h1{margin-bottom:.7rem;max-width:30ch}
.titulo .para{font-size:1.05rem}
.datos{display:grid;grid-template-columns:repeat(3,1fr);gap:1.2rem;margin-top:1.3rem;padding:.75rem 0;border-top:1px solid #d5dae3;border-bottom:1px solid #d5dae3}
.datos .k{font-size:.7rem;letter-spacing:.12em;text-transform:uppercase;color:#5f6b7d}
.datos .v{margin-top:.15rem;font-weight:600;font-variant-numeric:tabular-nums}

.contenido{margin-top:1.8rem}
.contenido ol{columns:2;column-gap:2.5rem;margin:.5rem 0 0;padding-left:1.4rem}
.contenido li{text-align:left;margin-bottom:.3rem;break-inside:avoid;padding-left:.3rem}
.carta{margin-top:2.4rem;padding-top:2rem;border-top:1px dashed #d5dae3}
.membrete.compacto{padding-bottom:.4rem;margin-bottom:1.6rem;border-bottom-width:1px}
.membrete.compacto .marca{font-size:1.1rem}
.membrete.compacto .emp{font-size:.72rem}
.carta .fecha{margin-bottom:1.2rem}
.carta .dest{margin-bottom:1.1rem;line-height:1.45}
.carta .dest div:nth-child(2){font-weight:600}
.carta .asunto{margin-bottom:1rem}
.carta .asunto b{font-weight:600}
.carta .saludo{margin-bottom:.8rem}
.firmante{margin-top:2.6rem;line-height:1.4}
.firmante .linea{width:16rem;border-top:1px solid #1c2230;padding-top:.4rem}
.firmante b{font-weight:600}

.salto{break-before:page}
.secciones{margin-top:2.4rem;padding-top:2rem;border-top:1px dashed #d5dae3}
ul,ol{margin:0 0 .8rem;padding-left:1.3rem}
li{margin-bottom:.35rem;padding-left:.15rem;text-align:justify;hyphens:auto}
li::marker{color:#1b2a41}
ol.pasos li{padding-left:.3rem}
.lt li b{font-weight:600}

table.t{width:100%;border-collapse:collapse;margin:.4rem 0 1rem;font-size:.92rem;line-height:1.4}
table.t th{text-align:left;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:#1b2a41;background:#f3f5f8;padding:.5rem .6rem;border-bottom:1.5px solid #1b2a41;vertical-align:bottom}
table.t td{padding:.55rem .6rem;border-bottom:1px solid #d5dae3;vertical-align:top}
table.t td:first-child{font-weight:600}
table.t tr{break-inside:avoid}
table.t .num{display:inline-block;min-width:1.3rem;color:#5f6b7d;font-weight:400;font-variant-numeric:tabular-nums}
table.precio td:last-child,table.precio th:last-child{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
table.precio td:first-child{font-weight:400}
table.precio tr.total td{font-weight:600;border-top:2px solid #1b2a41;border-bottom:0;font-size:1rem}
.nota{font-size:.85rem;color:#5f6b7d;margin-top:-.3rem}

.firmas{display:grid;grid-template-columns:1fr 1fr;gap:3rem;margin-top:1.6rem;break-inside:avoid}
.firmas h4{margin:0 0 .6rem;font-size:.75rem;letter-spacing:.12em;text-transform:uppercase;color:#1b2a41}
.firmas .campo{margin-top:1.55rem;border-bottom:1px solid #1c2230;padding-bottom:.15rem;font-size:.72rem;color:#5f6b7d;text-transform:uppercase;letter-spacing:.06em}

.pie{margin-top:2.5rem;padding-top:.8rem;border-top:1px solid #d5dae3;font-size:.78rem;color:#5f6b7d;display:flex;justify-content:space-between;gap:1rem;flex-wrap:wrap}
.fuera{max-width:8.5in;margin:.9rem auto 0;font-size:.8rem;color:var(--ground-text);text-align:center}

@media screen and (max-width:700px){
  .marco{padding:0}
  .hoja{padding:1.4rem 1.1rem 2rem;box-shadow:none}
  .membrete{flex-direction:column;align-items:flex-start;gap:.8rem}
  .emp{text-align:left}
  .datos,.firmas{grid-template-columns:1fr}
  table.t{display:block;overflow-x:auto}
  p,li{text-align:left;hyphens:manual}
}
@media print{
  html{font-size:10.5pt}
  body{background:#fff}
  .marco{padding:0}
  .hoja{max-width:none;padding:0;box-shadow:none}
  .secciones,.carta{margin-top:0;padding-top:0;border-top:0}
  .fuera{display:none}
  h2{margin-top:1.6rem}
  a{color:inherit;text-decoration:none}
}
"""

def bloques(bs, num):
    out = []; sub = 0; paso_ref = 0
    for b in bs:
        if "p" in b:
            out.append(f"<p>{e(b['p'])}</p>")
        elif "sub" in b:
            sub += 1
            out.append(f'<h3><span class="n">{num}.{sub}</span>{e(b["sub"])}</h3>')
            out.append(bloques(b["bloques"], f"{num}.{sub}"))
        elif "lista" in b:
            out.append("<ul>" + "".join(f"<li>{e(x)}</li>" for x in b["lista"]) + "</ul>")
        elif "lista_titulada" in b:
            out.append('<ul class="lt">' + "".join(f"<li><b>{e(t)}.</b> {e(d)}</li>" for t, d in b["lista_titulada"]) + "</ul>")
        elif "pasos" in b:
            out.append('<ol class="pasos">' + "".join(f"<li>{e(x)}</li>" for x in b["pasos"]) + "</ol>")
        elif "tabla" in b:
            t = b["tabla"]
            cg = "<colgroup>" + "".join(f'<col style="width:{w}%">' for w in t["anchos"]) + "</colgroup>"
            th = "<thead><tr>" + "".join(f"<th>{e(c)}</th>" for c in t["cols"]) + "</tr></thead>"
            rows = []
            for i, r in enumerate(t["filas"], 1):
                first = (f'<span class="num">{i}.</span>' if t.get("numerada") else "") + e(r[0])
                rows.append("<tr><td>" + first + "</td>" + "".join(f"<td>{e(c)}</td>" for c in r[1:]) + "</tr>")
            out.append(f'<table class="t">{cg}{th}<tbody>{"".join(rows)}</tbody></table>')
        elif "precio" in b:
            pr = b["precio"]
            rows = "".join(f"<tr><td>{e(c)}</td><td>{e(v)}</td></tr>" for c, v in pr["filas"])
            tot = f'<tr class="total"><td>{e(pr["total"][0])}</td><td>{e(pr["total"][1])}</td></tr>'
            out.append(f'<table class="t precio"><colgroup><col style="width:72%"><col style="width:28%"></colgroup><thead><tr><th>Concepto</th><th>Valor</th></tr></thead><tbody>{rows}{tot}</tbody></table>')
            out.append(f'<p class="nota">{e(pr["nota"])}</p>')
        elif "firmas" in b:
            f = b["firmas"]
            out.append('<div class="firmas">' + "".join(f"<div><h4>{e(pt)}</h4>" + "".join(f'<div class="campo">{e(c)}</div>' for c in f["campos"]) + "</div>" for pt in f["partes"]) + "</div>")
    return "\n".join(out)

C = D["carta"]
parts = [f"<title>Propuesta Vidrios y Espejos</title>",
  '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@600&family=Source+Sans+3:ital,wght@0,400;0,600;1,400&display=swap">',
  f"<style>{CSS}</style>", '<div class="marco"><article class="hoja" lang="es">']
parts.append(f'''<header class="membrete">
  <div><div class="marca">Creatv <b>Grow</b></div><div class="eyebrow">{e(M["proveedor_desc"])}</div></div>
  <div class="emp"><b>{e(M["razon_social"])}</b><br>{e(M["nit"])}<br>{e(M["web"])}<br>{e(M["correo"])} · {e(M["telefono"])}</div>
</header>''')
parts.append(f'''<section class="titulo">
  <div class="eyebrow">{e(M["titulo"])} N.º {e(M["numero"])}</div>
  <h1>{e(M["subtitulo"])}</h1>
  <p class="para">Preparada para <b>{e(M["cliente"])}</b><br><span class="muted">{e(M["cliente_desc"])}</span></p>
  <div class="datos">
    <div><div class="k">Fecha de emisión</div><div class="v">{e(M["fecha"])}</div></div>
    <div><div class="k">Vigencia</div><div class="v">{e(M["vigencia"])}</div></div>
    <div><div class="k">Valor del servicio</div><div class="v">{e(M["valor"])} {e(M["moneda"])} {e(M["periodo"])}</div></div>
  </div>
</section>''')
parts.append('<section class="contenido"><div class="eyebrow">Contenido</div><ol>' + "".join(f"<li>{e(sec['titulo'])}</li>" for sec in D["secciones"]) + "</ol></section>")
parts.append('<section class="carta salto">')
parts.append(f'<header class="membrete compacto"><div class="marca">Creatv <b>Grow</b></div><div class="emp">{e(M["titulo"])} N.º {e(M["numero"])}</div></header>')
parts.append(f'<p class="fecha">{e(M["ciudad_fecha"])}</p>')
parts.append('<div class="dest">' + "".join(f"<div>{e(l)}</div>" for l in C["destinatario"]) + "</div>")
parts.append(f'<p class="asunto"><b>Asunto:</b> {e(C["asunto"])}</p>')
parts.append(f'<p class="saludo">{e(C["saludo"])}</p>')
parts += [f"<p>{e(p)}</p>" for p in C["parrafos"]]
parts.append(f'<p>{e(C["despedida"])}</p>')
parts.append('<div class="firmante"><div class="linea"><b>' + e(C["firmante"][0]) + "</b><br>" + "<br>".join(e(x) for x in C["firmante"][1:]) + "</div></div>")
parts.append("</section>")
parts.append('<div class="secciones salto">')
for i, s in enumerate(D["secciones"], 1):
    parts.append(f'<section><h2><span class="n">{i}.</span>{e(s["titulo"])}</h2>' + bloques(s["bloques"], str(i)) + "</section>")
parts.append("</div>")
parts.append(f'<footer class="pie"><span>{e(M["proveedor"])} · {e(M["web"])} · {e(M["contacto"])} · {e(M["correo"])} · {e(M["telefono"])}</span><span>{e(M["titulo"])} N.º {e(M["numero"])}</span></footer>')
parts.append('</article></div>')
parts.append(f'<p class="fuera">Documento preparado por {e(M["proveedor"])} para {e(M["cliente"])}. {e(M["fecha"])}.</p>')
for n in ("propuesta.html", "propuesta_web.html"):
    open(os.path.join(H, n), "w").write("\n".join(parts))
print("html ok")
