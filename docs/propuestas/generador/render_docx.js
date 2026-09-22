const fs = require("fs"), path = require("path");
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType, AlignmentType,
  BorderStyle, LevelFormat, PageBreak, Footer, PageNumber, TabStopType, TableLayoutType } = require("docx");
const D = JSON.parse(fs.readFileSync(path.join(__dirname, "contenido.json"), "utf8"));
const M = D.meta, C = D.carta;
const NAVY = "1B2A41", INK = "1C2230", MUTED = "5F6B7D", RULE = "D5DAE3", PANEL = "F3F5F8", BLUE = "3F6FB8";
const SERIF = "Georgia", SANS = "Arial";
const PAGE_W = 12240, MARGIN = 1300, TEXT_W = PAGE_W - 2 * MARGIN;
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const noB = { top: none, bottom: none, left: none, right: none };
const noTB = { ...noB, insideHorizontal: none, insideVertical: none };
const line = (color = RULE, size = 4) => ({ style: BorderStyle.SINGLE, size, color });
const shade = (fill) => ({ type: ShadingType.CLEAR, color: "auto", fill });
const run = (text, o = {}) => new TextRun({ text, font: SANS, size: 22, color: INK, ...o });
const par = (children, o = {}) => new Paragraph({ spacing: { after: 140, line: 300 }, ...o, children: Array.isArray(children) ? children : [children] });
const p = (t, o = {}, ro = {}) => par(run(t, ro), { alignment: AlignmentType.JUSTIFIED, ...o });
const h2 = (n, t) => new Paragraph({ keepNext: true, spacing: { before: 400, after: 160 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 4 } },
  children: [new TextRun({ text: `${n}.  `, font: SERIF, size: 27, bold: true, color: NAVY }), new TextRun({ text: t, font: SERIF, size: 27, bold: true, color: NAVY })] });
const h3 = (n, t) => new Paragraph({ keepNext: true, spacing: { before: 260, after: 110 },
  children: [run(`${n}  `, { bold: true, color: MUTED }), run(t, { bold: true, color: NAVY })] });
const cell = (children, width, o = {}) => new TableCell({ width: { size: width, type: WidthType.DXA }, margins: { top: 100, bottom: 100, left: 120, right: 120 }, borders: noB, ...o, children });
const table = (widths, rows, o = {}) => new Table({ width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA }, columnWidths: widths, borders: noTB, layout: TableLayoutType.FIXED, ...o, rows });
let pasoRef = 0;

function bloques(bs, num, out) {
  let sub = 0;
  for (const b of bs) {
    if (b.p) out.push(p(b.p));
    else if (b.sub) { sub++; out.push(h3(`${num}.${sub}`, b.sub)); bloques(b.bloques, `${num}.${sub}`, out); }
    else if (b.lista) for (const x of b.lista) out.push(new Paragraph({ numbering: { reference: "bul", level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { after: 80, line: 290 }, children: [run(x)] }));
    else if (b.lista_titulada) for (const [t, d] of b.lista_titulada) out.push(new Paragraph({ numbering: { reference: "bul", level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { after: 90, line: 290 }, children: [run(t + ". ", { bold: true }), run(d)] }));
    else if (b.pasos) { const ref = `pasos${pasoRef++}`; for (const x of b.pasos) out.push(new Paragraph({ numbering: { reference: ref, level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { after: 80, line: 290 }, children: [run(x)] })); }
    else if (b.tabla) {
      const t = b.tabla; const ws = t.anchos.map((a) => Math.round(TEXT_W * a / 100)); ws[ws.length - 1] += TEXT_W - ws.reduce((a, c) => a + c, 0);
      const head = new TableRow({ tableHeader: true, children: t.cols.map((c, i) => cell([par(run(c.toUpperCase(), { bold: true, size: 16, color: NAVY, characterSpacing: 15 }), { spacing: { after: 0 } })], ws[i], { shading: shade(PANEL), borders: { ...noB, bottom: line(NAVY, 10) } })) });
      const rows = t.filas.map((r, i) => new TableRow({ cantSplit: true, children: r.map((c, j) => cell([par([...(j === 0 && t.numerada ? [run(`${i + 1}.  `, { size: 20, color: MUTED })] : []), run(c, { size: 20, bold: j === 0 })], { spacing: { after: 0, line: 280 } })], ws[j], { borders: { ...noB, bottom: line() } })) }));
      out.push(table(ws, [head, ...rows])); out.push(par(run(""), { spacing: { after: 60 } }));
    }
    else if (b.precio) {
      const pr = b.precio; const ws = [Math.round(TEXT_W * 0.72), TEXT_W - Math.round(TEXT_W * 0.72)];
      const head = new TableRow({ tableHeader: true, children: ["Concepto", "Valor"].map((c, i) => cell([par(run(c.toUpperCase(), { bold: true, size: 16, color: NAVY, characterSpacing: 15 }), { spacing: { after: 0 }, alignment: i ? AlignmentType.RIGHT : AlignmentType.LEFT })], ws[i], { shading: shade(PANEL), borders: { ...noB, bottom: line(NAVY, 10) } })) });
      const rows = pr.filas.map(([c, v]) => new TableRow({ cantSplit: true, children: [cell([par(run(c, { size: 20 }), { spacing: { after: 0 } })], ws[0], { borders: { ...noB, bottom: line() } }), cell([par(run(v, { size: 20 }), { spacing: { after: 0 }, alignment: AlignmentType.RIGHT })], ws[1], { borders: { ...noB, bottom: line() } })] }));
      const tot = new TableRow({ cantSplit: true, children: [cell([par(run(pr.total[0], { bold: true }), { spacing: { after: 0 } })], ws[0], { borders: { ...noB, top: line(NAVY, 12) } }), cell([par(run(pr.total[1], { bold: true }), { spacing: { after: 0 }, alignment: AlignmentType.RIGHT })], ws[1], { borders: { ...noB, top: line(NAVY, 12) } })] });
      out.push(table(ws, [head, ...rows, tot])); out.push(par(run(pr.nota, { size: 18, color: MUTED }), { spacing: { before: 80, after: 160 } }));
    }
    else if (b.firmas) {
      const f = b.firmas; const half = Math.floor((TEXT_W - 700) / 2);
      const col = (title) => new TableCell({ width: { size: half, type: WidthType.DXA }, borders: noB, margins: { top: 0, bottom: 0, left: 0, right: 0 }, children: [
        par(run(title.toUpperCase(), { bold: true, size: 16, color: NAVY, characterSpacing: 25 }), { spacing: { after: 120 } }),
        ...f.campos.map((c) => new Paragraph({ spacing: { before: 380, after: 0 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: INK, space: 2 } }, children: [run(c.toUpperCase(), { size: 14, color: MUTED, characterSpacing: 10 })] })) ] });
      out.push(table([half, 700, half], [new TableRow({ cantSplit: true, children: [col(f.partes[0]), new TableCell({ width: { size: 700, type: WidthType.DXA }, borders: noB, children: [par(run(""))] }), col(f.partes[1])] })]));
    }
  }
}

const ch = [];
// membrete
const lw = Math.round(TEXT_W * 0.55), rw = TEXT_W - lw;
ch.push(table([lw, rw], [new TableRow({ children: [
  cell([par([new TextRun({ text: "Creatv ", font: SERIF, size: 34, bold: true, color: NAVY }), new TextRun({ text: "Grow", font: SERIF, size: 34, bold: true, color: BLUE })], { spacing: { after: 40 } }),
        par(run(M.proveedor_desc.toUpperCase(), { size: 14, color: MUTED, characterSpacing: 25 }), { spacing: { after: 0 } })], lw, { margins: { top: 0, bottom: 140, left: 0, right: 0 }, borders: { ...noB, bottom: line(NAVY, 16) } }),
  cell([par(run(M.razon_social, { size: 16, bold: true }), { alignment: AlignmentType.RIGHT, spacing: { after: 0, line: 260 } }),
        par(run(M.nit, { size: 16, color: MUTED }), { alignment: AlignmentType.RIGHT, spacing: { after: 0, line: 260 } }),
        par(run(M.web, { size: 16, color: MUTED }), { alignment: AlignmentType.RIGHT, spacing: { after: 0, line: 260 } }),
        par(run(`${M.correo} · ${M.telefono}`, { size: 16, color: MUTED }), { alignment: AlignmentType.RIGHT, spacing: { after: 0, line: 260 } })], rw, { margins: { top: 0, bottom: 140, left: 0, right: 0 }, borders: { ...noB, bottom: line(NAVY, 16) }, verticalAlign: "bottom" }),
] })]));
// título
ch.push(par(run(`${M.titulo.toUpperCase()} N.º ${M.numero}`, { size: 15, bold: true, color: MUTED, characterSpacing: 30 }), { spacing: { before: 520, after: 160 } }));
ch.push(par(new TextRun({ text: M.subtitulo, font: SERIF, size: 36, bold: true, color: NAVY }), { spacing: { after: 200, line: 276 } }));
ch.push(par([run("Preparada para "), run(M.cliente, { bold: true })], { spacing: { after: 20 } }));
ch.push(par(run(M.cliente_desc, { color: MUTED }), { spacing: { after: 240 } }));
const dw = Math.floor(TEXT_W / 3);
ch.push(table([dw, dw, TEXT_W - 2 * dw], [new TableRow({ children: [["Fecha de emisión", M.fecha], ["Vigencia", M.vigencia], ["Valor del servicio", `${M.valor} ${M.moneda} ${M.periodo}`]].map(([k, v], i) =>
  cell([par(run(k.toUpperCase(), { size: 14, color: MUTED, characterSpacing: 25 }), { spacing: { after: 30 } }), par(run(v, { bold: true }), { spacing: { after: 0 } })], i < 2 ? dw : TEXT_W - 2 * dw, { margins: { top: 140, bottom: 140, left: 0, right: 160 }, borders: { ...noB, top: line(), bottom: line() } })) })]));
// contenido
ch.push(par(run("CONTENIDO", { size: 15, bold: true, color: MUTED, characterSpacing: 30 }), { spacing: { before: 420, after: 120 } }));
D.secciones.forEach((s, i) => ch.push(par([run(`${i + 1}.  `, { color: NAVY }), run(s.titulo)], { spacing: { after: 40, line: 290 }, indent: { left: 200 } })));
ch.push(new Paragraph({ children: [new PageBreak()] }));
// carta (membrete compacto)
ch.push(new Paragraph({ tabStops: [{ type: TabStopType.RIGHT, position: TEXT_W }], spacing: { after: 360 }, border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: NAVY, space: 6 } },
  children: [new TextRun({ text: "Creatv ", font: SERIF, size: 26, bold: true, color: NAVY }), new TextRun({ text: "Grow", font: SERIF, size: 26, bold: true, color: BLUE }), run("\t", { size: 16 }), run(`${M.titulo} N.º ${M.numero}`, { size: 16, color: MUTED })] }));
ch.push(par(run(M.ciudad_fecha), { spacing: { before: 0, after: 260 } }));
C.destinatario.forEach((l, i) => ch.push(par(run(l, { bold: i === 1 }), { spacing: { after: 0, line: 280 } })));
ch.push(par([run("Asunto: ", { bold: true }), run(C.asunto)], { spacing: { before: 260, after: 220 }, alignment: AlignmentType.JUSTIFIED }));
ch.push(par(run(C.saludo), { spacing: { after: 180 } }));
C.parrafos.forEach((t) => ch.push(p(t, { spacing: { after: 180, line: 300 } })));
ch.push(par(run(C.despedida), { spacing: { before: 60, after: 700 } }));
ch.push(new Paragraph({ spacing: { after: 0 }, border: { top: { style: BorderStyle.SINGLE, size: 6, color: INK, space: 6 } }, indent: { right: TEXT_W - 4600 }, children: [run(C.firmante[0], { bold: true })] }));
C.firmante.slice(1).forEach((t) => ch.push(par(run(t, { color: MUTED }), { spacing: { after: 0, line: 280 } })));
ch.push(new Paragraph({ children: [new PageBreak()] }));
// secciones
D.secciones.forEach((s, i) => { ch.push(h2(i + 1, s.titulo)); bloques(s.bloques, String(i + 1), ch); });

const numbering = { config: [
  { reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 400, hanging: 260 } }, run: { color: NAVY } } }] },
  ...Array.from({ length: 8 }, (_, i) => ({ reference: `pasos${i}`, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 440, hanging: 300 } }, run: { color: NAVY } } }] })),
] };

const doc = new Document({
  creator: M.proveedor, title: `${M.titulo} ${M.numero}`, description: M.subtitulo,
  styles: { default: { document: { run: { font: SANS, size: 22, color: INK } } } },
  numbering,
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: 15840 }, margin: { top: 1150, bottom: 1150, left: MARGIN, right: MARGIN, footer: 560 } } },
    footers: { default: new Footer({ children: [new Paragraph({ tabStops: [{ type: TabStopType.RIGHT, position: TEXT_W }], border: { top: { style: BorderStyle.SINGLE, size: 4, color: RULE, space: 6 } }, spacing: { after: 0 },
      children: [run(`${M.titulo} N.º ${M.numero} · ${M.proveedor}`, { size: 15, color: MUTED }), run("\t", { size: 15 }), new TextRun({ font: SANS, size: 15, color: MUTED, children: ["Página ", PageNumber.CURRENT, " de ", PageNumber.TOTAL_PAGES] })] })] }) },
    children: ch,
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(path.join(__dirname, "propuesta.docx"), buf); console.log("docx ok", buf.length, "bytes"); });
