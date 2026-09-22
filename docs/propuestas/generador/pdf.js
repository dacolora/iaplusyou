const puppeteer = require("puppeteer-core");
const path = require("path");
const M = require("./contenido.json").meta;
(async () => {
  const browser = await puppeteer.launch({ executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", headless: true });
  const page = await browser.newPage();
  await page.goto("file://" + path.join(__dirname, "propuesta.html"), { waitUntil: "networkidle0", timeout: 60000 });
  await page.evaluateHandle("document.fonts.ready");
  const st = "font-family:Arial,Helvetica,sans-serif;font-size:7.5pt;color:#6b7383;width:100%;padding:0 0.9in;display:flex;justify-content:space-between;";
  await page.pdf({
    path: path.join(__dirname, "propuesta.pdf"), format: "Letter", printBackground: true,
    margin: { top: "0.8in", bottom: "0.9in", left: "0.9in", right: "0.9in" },
    displayHeaderFooter: true,
    headerTemplate: `<div style="${st}"><span></span><span></span></div>`,
    footerTemplate: `<div style="${st}"><span>${M.titulo} N.º ${M.numero} · ${M.proveedor}</span><span>Página <span class="pageNumber"></span> de <span class="totalPages"></span></span></div>`,
  });
  await browser.close();
  console.log("pdf ok");
})().catch((err) => { console.error(err); process.exit(1); });
