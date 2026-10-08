/* Centro de resultados de Experimentos (E2, maqueta aprobada 2026-10-02).
   Pide el fragmento (exp_resultados) al entrar a la pestaña y al cambiar un filtro (el filtro vive en el hash:
   #experimentos?dias=&exp=&pais=&pieza=&tipo=&moneda=), abre el panel de una pieza (exp_pieza) y dibuja las gráficas
   en SVG. ES5, sin librerías. Reglas: los datos entran SOLO con textContent/setAttribute; innerHTML solo con los
   fragmentos que manda el servidor (ya escapados por Jinja). Los colores van por clases (pantallas/experimentos.css);
   los avisos se posicionan dentro de su contenedor, nunca fijos a la ventana. */
(function () {
  'use strict';
  if (window.CentroResultados) return;
  var NS = 'http://www.w3.org/2000/svg';
  var LANG = document.documentElement.lang || 'es';

  function numero(v) { return typeof v === 'number' && isFinite(v); }
  function lista(v) { return Array.isArray(v) ? v : []; }
  function json(s, defecto) { try { var v = JSON.parse(s); return v === null || v === undefined ? defecto : v; } catch (e) { return defecto; } }
  function vaciar(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function svg(tag, attrs, padre, texto) {
    var el = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    if (texto !== undefined) el.textContent = texto;
    if (padre) padre.appendChild(el);
    return el;
  }
  function textosDe(id) {
    var el = document.getElementById(id);
    return el ? json(el.textContent, {}) : {};
  }

  // ---------- formatos ----------
  function fmt(v, decimales) {
    if (!numero(v)) return '—';
    return v.toLocaleString(LANG, { minimumFractionDigits: decimales || 0, maximumFractionDigits: decimales || 0 });
  }
  // Etiqueta corta para un eje: 1,2 M / 250 k / 12.
  function corto(v) {
    if (!numero(v)) return '—';
    var a = Math.abs(v);
    if (a >= 1e6) return fmt(v / 1e6, a >= 1e7 ? 0 : 1) + ' M';
    if (a >= 1e3) return fmt(v / 1e3, a >= 1e4 ? 0 : 1) + ' k';
    return fmt(v, a < 10 && a !== Math.round(a) ? 2 : 0);
  }
  // Cómo se escribe cada métrica en ejes y avisos.
  function valorMetrica(metrica, v, enEje) {
    if (!numero(v)) return '—';
    if (metrica === 'ctr' || metrica === 'gancho') return fmt(v, enEje ? (v < 10 ? 1 : 0) : 2) + ' %';
    if (metrica === 'roas') return fmt(v, enEje ? 1 : 2) + '×';
    if (metrica === 'frecuencia') return fmt(v, 2);
    return enEje ? corto(v) : fmt(v, Math.abs(v) >= 1000 ? 0 : 2);   // gasto, cpc, cpm: dinero
  }
  function fecha(iso) {
    var p = String(iso || '').split('-');
    if (p.length < 3) return String(iso || '');
    var d = new Date(+p[0], +p[1] - 1, +p[2]);
    try { return d.toLocaleDateString(LANG, { day: 'numeric', month: 'short' }); } catch (e) { return p[2] + '/' + p[1]; }
  }

  function escala(valores) {
    var max = 0;
    valores.forEach(function (v) { if (numero(v)) max = Math.max(max, v); });
    if (!max) return 1;
    var potencia = Math.pow(10, Math.floor(Math.log(max) / Math.LN10));
    var pasos = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
    for (var i = 0; i < pasos.length; i++) if (pasos[i] * potencia >= max) return pasos[i] * potencia;
    return 10 * potencia;
  }
  // Un hueco corta la línea; null nunca se convierte en cero.
  function trazado(valores, x, y, escalones) {
    var d = '', abierto = false;
    valores.forEach(function (v, i) {
      if (!numero(v)) { abierto = false; return; }
      d += (abierto ? (escalones ? ' H' + x(i) + ' V' : ' L' + x(i) + ',') : ' M' + x(i) + ',') + y(v);
      abierto = true;
    });
    return d.trim();
  }
  // El ancho real de la caja: las gráficas con texto se dibujan a su tamaño (letra legible en el celular).
  function ancho(el, defecto) {
    var w = el.clientWidth || (el.parentNode && el.parentNode.clientWidth) || 0;
    return Math.max(240, Math.round(w || defecto));
  }
  function lienzo(el, w, h) {
    var s = el.tagName.toLowerCase() === 'svg' ? el : null;
    vaciar(el);
    if (!s) s = svg('svg', { 'class': 'cr-svg' }, el);
    s.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    return s;
  }

  // ---------- avisos ----------
  // Un div.cr-aviso dentro de la caja de la gráfica (position: relative por CSS), con fecha y valor.
  function cajaDe(el) {
    var caja = el.tagName.toLowerCase() === 'svg' ? el.parentNode : el;
    if (caja && caja.classList) caja.classList.add('cr-con-aviso');
    return caja;
  }
  function mostrarAviso(caja, objetivo, texto) {
    if (!caja) return;
    var tip = caja.querySelector(':scope > .cr-aviso');
    if (!tip) { tip = document.createElement('div'); tip.className = 'cr-aviso'; tip.setAttribute('role', 'status'); caja.appendChild(tip); }
    tip.textContent = texto;
    tip.hidden = false;
    var r = objetivo.getBoundingClientRect(), c = caja.getBoundingClientRect();
    var x = r.left - c.left + r.width / 2 - tip.offsetWidth / 2;
    var y = r.top - c.top - tip.offsetHeight - 6;
    tip.style.left = Math.max(0, Math.min(x, c.width - tip.offsetWidth)) + 'px';
    tip.style.top = Math.max(0, y) + 'px';
  }
  function ocultarAviso(caja) {
    var tip = caja && caja.querySelector(':scope > .cr-aviso');
    if (tip) tip.hidden = true;
  }
  // Cada punto: <title> (lectores de pantalla) + aviso al pasar el mouse, al tocar o con el foco.
  function conAviso(punto, caja, texto, alEntrar, alSalir) {
    svg('title', {}, punto, texto);
    function entrar() { if (alEntrar) alEntrar(); mostrarAviso(caja, punto, texto); }
    function salir() { if (alSalir) alSalir(); ocultarAviso(caja); }
    punto.addEventListener('pointerenter', entrar);
    punto.addEventListener('pointerdown', entrar);
    punto.addEventListener('focus', entrar);
    punto.addEventListener('pointerleave', salir);
    punto.addEventListener('blur', salir);
  }

  // ---------- gráficas ----------
  // Día a día: barras = gasto, línea = la métrica elegida (dos ejes rotulados); marcas punteadas donde el motor actuó.
  function grafDia(el, datos, metrica, textos) {
    var serie = datos.serie || {}, dias = lista(serie.dias), gastos = lista(serie.gasto), valores = lista(serie[metrica]);
    var n = dias.length;
    var hay = gastos.some(function (g) { return numero(g) && g > 0; }) || valores.some(numero);
    if (!n || !hay) { vaciar(el); var p = document.createElement('p'); p.className = 'cr-vacio'; p.textContent = textos.sinDatos || '—'; el.appendChild(p); return; }
    var W = ancho(el, 720), H = W < 520 ? 210 : 250;
    var izq = W < 520 ? 40 : 52, der = W < 520 ? 40 : 52, arriba = 26, abajo = 24;
    var base = H - abajo, alto = base - arriba, anchoUtil = W - izq - der;
    var s = lienzo(el, W, H);
    var maxG = escala(gastos), maxV = escala(valores.slice(0, n));
    var paso = anchoUtil / n;
    var x = function (i) { return izq + (i + 0.5) * paso; };
    var yG = function (v) { return base - Math.max(0, v) / maxG * alto; };
    var yV = function (v) { return base - Math.max(0, v) / maxV * alto; };
    var nombre = textos[metrica] || metrica.toUpperCase();
    var nombreGasto = (textos.gasto || '') + (serie.moneda ? ' · ' + serie.moneda : '');
    s.setAttribute('aria-label', nombreGasto + ' · ' + nombre);
    svg('text', { x: izq, y: 12, 'class': 'cr-eje cr-eje-titulo' }, s, nombreGasto);
    svg('text', { x: W - der, y: 12, 'text-anchor': 'end', 'class': 'cr-eje cr-eje-titulo cr-eje-linea' }, s, nombre);
    for (var k = 0; k <= 4; k++) {
      var yy = base - k * alto / 4;
      svg('line', { x1: izq, x2: W - der, y1: yy, y2: yy, 'class': k ? 'cr-rejilla' : 'cr-rejilla cr-rejilla-base' }, s);
      svg('text', { x: izq - 6, y: yy + 3, 'text-anchor': 'end', 'class': 'cr-eje' }, s, corto(k * maxG / 4));
      svg('text', { x: W - der + 6, y: yy + 3, 'class': 'cr-eje cr-eje-linea' }, s, valorMetrica(metrica, k * maxV / 4, true));
    }
    // Una fecha cada ~64 px (cada 5 días en un periodo de 14 a 30 en escritorio) y la de hoy si cabe.
    var barras = [], cadaCuanto = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(anchoUtil / 64)))), ultimaEtiqueta = -cadaCuanto;
    dias.forEach(function (d, j) {
      var g = gastos[j];
      barras.push(numero(g) && g > 0 ? svg('rect', { x: x(j) - paso * 0.32, y: yG(g), width: Math.max(1, paso * 0.64), height: base - yG(g), rx: 2, 'class': 'cr-barra-dia' }, s) : null);
      if (j % cadaCuanto === 0 || (j === n - 1 && j - ultimaEtiqueta >= cadaCuanto * 0.6)) {
        svg('text', { x: x(j), y: H - 6, 'text-anchor': 'middle', 'class': 'cr-eje' }, s, fecha(d));
        ultimaEtiqueta = j;
      }
    });
    svg('path', { d: trazado(valores.slice(0, n), x, yV, false), 'class': 'cr-linea' }, s);
    if (n <= 45) valores.slice(0, n).forEach(function (v, j) { if (numero(v)) svg('circle', { cx: x(j), cy: yV(v), r: 2.6, 'class': 'cr-punto' }, s); });
    // Marcas: días en que el motor actuó (varias del mismo día van juntas).
    var porDia = {};
    lista(datos.marcas).forEach(function (m) { if (m && dias.indexOf(m.dia) >= 0) (porDia[m.dia] = porDia[m.dia] || []).push(m.texto); });
    var caja = cajaDe(el);
    Object.keys(porDia).forEach(function (dia) {
      var j = dias.indexOf(dia);
      svg('line', { x1: x(j), x2: x(j), y1: arriba - 4, y2: base, 'class': 'cr-marca' }, s);
      var punto = svg('circle', { cx: x(j), cy: arriba - 4, r: 5, 'class': 'cr-marca-punto', tabindex: 0 }, s);
      conAviso(punto, caja, fecha(dia) + '\n' + porDia[dia].join('\n'));
    });
    // Zonas por día: el aviso con la fecha, el gasto y la métrica.
    dias.forEach(function (d, j) {
      var zona = svg('rect', { x: izq + j * paso, y: arriba, width: paso, height: alto, 'class': 'cr-zona' }, s);
      var texto = fecha(d) + '\n' + (textos.gasto || '') + ': ' + valorMetrica('gasto', gastos[j]) + (serie.moneda ? ' ' + serie.moneda : '') +
        '\n' + nombre + ': ' + valorMetrica(metrica, valores[j]);
      conAviso(zona, caja, texto, function () { if (barras[j]) barras[j].classList.add('activa'); },
        function () { if (barras[j]) barras[j].classList.remove('activa'); });
    });
    // Las marcas quedan encima de las zonas para que su aviso se alcance.
    s.querySelectorAll('.cr-marca-punto').forEach(function (m) { s.appendChild(m); });
  }

  // Tendencia de un indicador: solo la forma, sin ejes.
  function grafSpark(el, valores) {
    valores = lista(valores);
    var utiles = valores.filter(numero);
    var s = lienzo(el, 72, 24);
    el.classList.toggle('cr-sin-tendencia', utiles.length < 2);
    if (utiles.length < 2) return;
    var min = Math.min.apply(null, utiles), max = Math.max.apply(null, utiles), rango = max - min || 1;
    var n = valores.length;
    var x = function (i) { return n < 2 ? 36 : 1 + i * 70 / (n - 1); };
    var y = function (v) { return 22 - (v - min) / rango * 20; };
    svg('path', { d: trazado(valores, x, y, false), 'class': 'cr-spark-linea' }, s);
  }

  // Evolución de una pieza: su métrica día a día y, punteada, la del experimento entero.
  function grafEvolucion(el, d, dias, textos) {
    var serie = lista(d.serie), promedio = lista(d.promedio), n = Math.max(serie.length, promedio.length);
    var W = ancho(el, 300), H = 56;
    var s = lienzo(el, W, H);
    if (!serie.some(numero) && !promedio.some(numero)) { el.classList.add('cr-sin-tendencia'); return; }
    el.classList.remove('cr-sin-tendencia');
    // Escala del mínimo al máximo de las dos líneas (como la maqueta): lo que importa es el rumbo contra el promedio.
    var todos = serie.concat(promedio).filter(numero);
    var min = Math.min.apply(null, todos), max = Math.max.apply(null, todos), holgura = (max - min) * 0.15 || Math.abs(max) * 0.1 || 1;
    min -= holgura; max += holgura;
    var x = function (i) { return n < 2 ? W / 2 : 4 + i * (W - 8) / (n - 1); };
    var y = function (v) { return H - 4 - (v - min) / (max - min) * (H - 10); };
    svg('path', { d: trazado(promedio, x, y, false), 'class': 'cr-promedio' }, s);
    svg('path', { d: trazado(serie, x, y, false), 'class': 'cr-linea' }, s);
    var ultimo = -1;
    serie.forEach(function (v, i) { if (numero(v)) ultimo = i; });
    if (ultimo >= 0) svg('circle', { cx: x(ultimo), cy: y(serie[ultimo]), r: 3, 'class': 'cr-punto' }, s);
    var caja = cajaDe(el), metrica = d.metrica || 'ctr', paso = n ? W / n : W;
    for (var i = 0; i < n; i++) {
      if (!numero(serie[i]) && !numero(promedio[i])) continue;
      var zona = svg('rect', { x: i * paso, y: 0, width: paso, height: H, 'class': 'cr-zona' }, s);
      conAviso(zona, caja, (dias[i] ? fecha(dias[i]) + '\n' : '') + (textos[metrica] || metrica.toUpperCase()) + ': ' +
        valorMetrica(metrica, serie[i]) + '\n' + (textos.promedio || '') + ': ' + valorMetrica(metrica, promedio[i]));
    }
  }

  // Dona de partes (ubicaciones): mismo orden y color que la leyenda de la plantilla (cr-serie-1…8).
  function grafDona(el, filas) {
    filas = lista(filas);
    var valores = filas.map(function (f) { return numero(f) ? f : (f && numero(f.pct_gasto) ? f.pct_gasto : (f && numero(f.gasto) ? f.gasto : 0)); });
    var total = valores.reduce(function (a, v) { return a + Math.max(0, v); }, 0);
    var s = lienzo(el, 100, 100), largo = 2 * Math.PI * 36, inicio = 0, caja = cajaDe(el);
    svg('circle', { cx: 50, cy: 50, r: 36, 'class': 'cr-dona-fondo' }, s);
    if (!total) return;
    valores.forEach(function (v, i) {
      if (!(v > 0)) return;
      var parte = v / total * largo;
      var arco = svg('circle', { cx: 50, cy: 50, r: 36, 'class': 'cr-dona-arco cr-serie-' + ((i % 8) + 1),
        'stroke-dasharray': parte + ' ' + (largo - parte), 'stroke-dashoffset': -inicio, transform: 'rotate(-90 50 50)' }, s);
      conAviso(arco, caja, ((filas[i] && filas[i].etiqueta) || '') + ': ' + fmt(v / total * 100, 1) + ' %');
      inicio += parte;
    });
  }

  // Tope usado de un experimento: un arco y el porcentaje al centro.
  function grafDonaPct(el, pct) {
    pct = Math.max(0, Math.min(100, numero(pct) ? pct : 0));
    var s = lienzo(el, 44, 44), largo = 2 * Math.PI * 18;
    svg('circle', { cx: 22, cy: 22, r: 18, 'class': 'cr-dona-fondo' }, s);
    if (pct > 0) svg('circle', { cx: 22, cy: 22, r: 18, 'class': 'cr-dona-arco' + (pct >= 90 ? ' cr-dona-lleno' : ''),
      'stroke-dasharray': (pct / 100 * largo) + ' ' + largo, transform: 'rotate(-90 22 22)' }, s);
    svg('text', { x: 22, y: 25.5, 'text-anchor': 'middle', 'class': 'cr-dona-texto' }, s, Math.round(pct) + '%');
  }

  // Retención del video: escalones que bajan (3 s, 25 %, 50 %, 75 %, 95 %, 100 %).
  function grafCurva(el, puntos) {
    puntos = lista(puntos);
    var W = ancho(el, 320), H = 130, izq = 8, der = 8, arriba = 18, abajo = 22, base = H - abajo;
    var s = lienzo(el, W, H), n = puntos.length;
    if (!n) return;
    var paso = (W - izq - der) / n, caja = cajaDe(el);
    var y = function (v) { return base - Math.max(0, Math.min(100, v)) / 100 * (base - arriba); };
    svg('line', { x1: izq, x2: W - der, y1: base, y2: base, 'class': 'cr-rejilla cr-rejilla-base' }, s);
    puntos.forEach(function (p, i) {
      var v = Array.isArray(p) ? p[1] : p, etiqueta = Array.isArray(p) ? p[0] : '';
      if (!numero(v)) return;
      var x0 = izq + i * paso;
      var r = svg('rect', { x: x0 + 1, y: y(v), width: Math.max(1, paso - 2), height: base - y(v), rx: 2, 'class': 'cr-curva-escalon' }, s);
      svg('text', { x: x0 + paso / 2, y: y(v) - 4, 'text-anchor': 'middle', 'class': 'cr-eje cr-eje-linea' }, s, fmt(v, v < 10 ? 1 : 0) + ' %');
      svg('text', { x: x0 + paso / 2, y: H - 6, 'text-anchor': 'middle', 'class': 'cr-eje' }, s, etiqueta);
      conAviso(r, caja, etiqueta + ': ' + fmt(v, 1) + ' %');
    });
  }

  // Dibuja todo lo que haya bajo `raiz` (el fragmento o el cuerpo del panel).
  // `fuente`: dónde buscar el JSON de las gráficas si no está bajo `raiz` (las tarjetas de «Ver todas»).
  function dibujar(raiz, fuente) {
    if (!raiz || !raiz.querySelectorAll) return;
    var textos = textosDe('cr-textos');
    var bloque = (fuente || raiz).querySelector('#cr-datos, .cr-datos-pieza');
    var datos = bloque ? json(bloque.textContent, {}) : {};
    raiz.querySelectorAll('[data-cr-metrica]').forEach(function (b) { textos[b.getAttribute('data-cr-metrica')] = b.textContent.trim(); });
    var dias = lista((datos.serie || {}).dias);
    raiz.querySelectorAll('[data-cr-grafico]').forEach(function (el) { grafDia(el, datos, el.getAttribute('data-metrica') || 'ctr', textos); });
    raiz.querySelectorAll('[data-cr-spark]').forEach(function (el) { grafSpark(el, json(el.getAttribute('data-cr-spark'), [])); });
    raiz.querySelectorAll('[data-cr-evolucion]').forEach(function (el) { grafEvolucion(el, json(el.getAttribute('data-cr-evolucion'), {}), dias, textos); });
    raiz.querySelectorAll('[data-cr-dona]').forEach(function (el) { grafDona(el, json(el.getAttribute('data-cr-dona'), [])); });
    raiz.querySelectorAll('[data-cr-dona-pct]').forEach(function (el) { grafDonaPct(el, json(el.getAttribute('data-cr-dona-pct'), 0)); });
    raiz.querySelectorAll('[data-cr-curva]').forEach(function (el) { grafCurva(el, json(el.getAttribute('data-cr-curva'), [])); });
  }
  var dibujarPieza = dibujar;

  // ---------- carga, filtros y panel ----------
  function iniciar() {
    var raiz = document.getElementById('cr-resultados');
    if (!raiz || raiz.getAttribute('data-cr-iniciado')) return;
    raiz.setAttribute('data-cr-iniciado', '1');
    var textos = textosDe('cr-textos');
    var panel = document.getElementById('cr-panel'), cuerpo = panel && panel.querySelector('.cr-panel-cuerpo');
    var pedido = 0, ultima = null, panelPedido = 0, foco = null, irArriba = false;

    function aviso(host, mensaje, reintentar) {
      vaciar(host);
      var caja = document.createElement('div'); caja.className = 'estado-vacio';
      var p = document.createElement('p'); p.className = 'estado-vacio-titulo'; p.textContent = mensaje; caja.appendChild(p);
      if (reintentar) {
        var b = document.createElement('button'); b.type = 'button'; b.className = 'btn-sm';
        b.textContent = textos.reintentar || '↻'; b.addEventListener('click', reintentar); caja.appendChild(b);
      }
      host.appendChild(caja);
    }
    // Un fragmento que no es el esperado (p. ej. la sesión venció y el fetch siguió hasta el login) es un error:
    // nunca se mete otra página dentro de la pestaña.
    function pedir(url, marca) {
      return fetch(url, { headers: { 'X-Requested-With': 'fetch' }, cache: 'no-store', credentials: 'same-origin' })
        .then(function (r) {
          if (!r.ok || r.redirected) throw new Error(String(r.ok ? 'redirigido' : r.status));
          return r.text();
        })
        .then(function (html) { if (html.indexOf(marca) < 0) throw new Error('otro'); return html; });
    }
    function cargar(query, forzar) {
      if (!forzar && ultima === query) return;
      ultima = query;
      var n = ++pedido;
      raiz.setAttribute('aria-busy', 'true');
      if (raiz.querySelector('.cr-resultados-fragmento')) raiz.classList.add('cr-actualizando');
      else aviso(raiz, textos.cargando || '…');
      pedir(raiz.getAttribute('data-url') + (query ? '?' + query : ''), 'cr-resultados-fragmento').then(function (html) {
        if (n !== pedido) return;
        var activo = document.activeElement;
        var hrefFoco = activo && raiz.contains(activo) && activo.getAttribute ? activo.getAttribute('href') : null;
        raiz.innerHTML = html;          // fragmento del servidor (autoescape de Jinja); los datos de las gráficas van por textContent
        raiz.classList.remove('cr-actualizando');
        raiz.setAttribute('aria-busy', 'false');
        if (hrefFoco) {
          var enlaces = raiz.querySelectorAll('[data-cr-filtro]'), destinoFoco = null;
          enlaces.forEach(function (a) { if (!destinoFoco && a.getAttribute('href') === hrefFoco) destinoFoco = a; });
          if (!destinoFoco) destinoFoco = raiz.querySelector('.cr-filtros [data-cr-filtro]');
          if (destinoFoco) destinoFoco.focus();
        }
        dibujar(raiz);
        if (window.arrancarSondeos) window.arrancarSondeos(raiz);
        if (irArriba) { irArriba = false; raiz.scrollIntoView({ block: 'start', behavior: 'smooth' }); }
      }).catch(function () {
        if (n !== pedido) return;
        ultima = null;
        raiz.classList.remove('cr-actualizando');
        raiz.setAttribute('aria-busy', 'false');
        aviso(raiz, textos.error || '…', function () { cargar(query, true); });
      });
    }
    function pestanaActiva() {
      var tab = document.getElementById('tab-experimentos');
      return !!(tab && tab.classList.contains('activo'));
    }
    function navegar() {
      if (panel && panel.open) panel.close();     // otro filtro, atrás o adelante: el panel era de la vista anterior
      var hash = location.hash.slice(1), corte = hash.indexOf('?');
      var nombre = corte < 0 ? hash : hash.slice(0, corte);
      if (['experimentos', 'tablero', 'ads'].indexOf(nombre) < 0 && !(nombre === '' && pestanaActiva())) {
        pedido++; ultima = null;        // fuera de la pestaña: se cancela lo pendiente y al volver se pide de nuevo
        return;
      }
      var query = new URLSearchParams(corte < 0 ? '' : hash.slice(corte + 1));
      if (query.has('piezas') && raiz.getAttribute('data-url-nuevo')) {
        location.replace(raiz.getAttribute('data-url-nuevo') + '?piezas=' + encodeURIComponent(query.get('piezas')));
        return;
      }
      cargar(query.toString());
    }
    // Compatibilidad con los enlaces viejos ?exp=<id>#experimentos (p. ej. _tw_panel.html): se pasa UNA vez al hash y
    // se quita de la dirección. Si navegar() lo releyera de location.search, el filtro no se podría quitar nunca
    // (ni con su «×», ni con «Todos los experimentos», ni con el menú lateral). Revisión de R2, 2026-10-03.
    function consumirExpViejo() {
      var busqueda = new URLSearchParams(location.search), exp = busqueda.get('exp');
      var hash = location.hash.slice(1), nombre = hash.split('?')[0];
      if (!exp || hash.indexOf('?') >= 0) return;
      if (['experimentos', 'tablero', 'ads'].indexOf(nombre) < 0 && !(nombre === '' && pestanaActiva())) return;
      busqueda.delete('exp');
      var resto = busqueda.toString();
      history.replaceState(null, '', location.pathname + (resto ? '?' + resto : '') + '#experimentos?exp=' + encodeURIComponent(exp));
    }
    function abrir(url, origen) {
      if (!panel || !cuerpo) return;
      foco = origen;
      var n = ++panelPedido;
      aviso(cuerpo, textos.cargandoPieza || textos.cargando || '…');
      if (!panel.open) panel.showModal();
      pedir(url, 'cr-pieza-fragmento').then(function (html) {
        if (n !== panelPedido || !panel.open) return;
        cuerpo.innerHTML = html;        // fragmento del servidor (autoescape de Jinja)
        dibujarPieza(cuerpo);
        if (window.arrancarSondeos) window.arrancarSondeos(cuerpo);
      }).catch(function (err) {
        if (n !== panelPedido || !panel.open) return;
        aviso(cuerpo, err && err.message === '404' ? (textos.piezaNoExiste || '…') : (textos.errorPieza || '…'),
          err && err.message === '404' ? null : function () { abrir(url, origen); });
      });
    }
    function cerrarMenus(salvo) {
      raiz.querySelectorAll('details.cr-menu[open]').forEach(function (d) { if (d !== salvo) d.open = false; });
    }

    if (panel) {
      panel.addEventListener('close', function () {
        panelPedido++;
        cuerpo.querySelectorAll('video, audio').forEach(function (v) { try { v.pause(); } catch (e) { /* nada */ } });
        if (foco && foco.isConnected) foco.focus();
      });
      // Clic en el fondo (fuera del cajón) cierra.
      panel.addEventListener('click', function (ev) {
        if (ev.target !== panel) return;
        var r = panel.getBoundingClientRect();
        if (ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom) panel.close();
      });
    }
    raiz.addEventListener('toggle', function (ev) {
      var d = ev.target;
      if (d && d.matches && d.matches('details.cr-menu') && d.open) cerrarMenus(d);
      if (d && d.matches && d.matches('details.cr-mas') && d.open) dibujar(d, raiz);   // las tarjetas recién visibles ya tienen ancho
    }, true);
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') cerrarMenus(null);
      var fila = ev.target.closest && ev.target.closest('tr[data-cr-pieza]');
      if (fila && ev.target === fila && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); abrir(fila.getAttribute('data-cr-pieza'), fila); }
    });
    document.addEventListener('click', function (ev) {
      if (!ev.target.closest) return;
      if (!ev.target.closest('details.cr-menu')) cerrarMenus(null);
      var b = ev.target.closest('[data-cr-filtro], [data-cr-pieza], [data-cr-metrica], .cr-panel-cerrar');
      var enPanel = panel && b && panel.contains(b);
      if (!b || (!raiz.contains(b) && !enPanel)) {
        // Un enlace del panel que lleva a otra pestaña («Ver en Crear»): el panel se cierra.
        var a = ev.target.closest('a[href]');
        if (a && panel && panel.open && panel.contains(a) && a.target !== '_blank') panel.close();   // «¿Por qué?» abre otra pestaña
        return;
      }
      if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey || ev.button > 0) return;
      // Dentro de una fila, un control propio (botón, enlace, formulario) manda sobre la fila.
      var control = ev.target.closest('a, button, input, select, textarea, form, summary');
      if (b.hasAttribute('data-cr-pieza') && b.tagName === 'TR' && control && b.contains(control)) return;
      ev.preventDefault();
      if (b.hasAttribute('data-cr-filtro')) {
        cerrarMenus(null);
        irArriba = !b.closest('.cr-filtros') && !b.closest('.estado-vacio');
        if (enPanel) panel.close();
        history.pushState(null, '', b.getAttribute('href'));
        navegar();                      // sin hashchange: la pestaña no salta arriba con cada filtro
      } else if (b.hasAttribute('data-cr-pieza')) {
        abrir(b.getAttribute('data-cr-pieza'), b);
      } else if (b.hasAttribute('data-cr-metrica')) {
        var host = enPanel ? cuerpo : raiz, grupo = b.parentNode;
        grupo.querySelectorAll('[data-cr-metrica]').forEach(function (otro) {
          otro.setAttribute('aria-pressed', String(otro === b));
          otro.classList.toggle('activo', otro === b);
        });
        host.querySelectorAll('[data-cr-grafico]').forEach(function (el) { el.setAttribute('data-metrica', b.getAttribute('data-cr-metrica')); });
        var bloque = host.querySelector('#cr-datos, .cr-datos-pieza'), datos = bloque ? json(bloque.textContent, {}) : {};
        var t = textosDe('cr-textos');
        host.querySelectorAll('[data-cr-metrica]').forEach(function (x) { t[x.getAttribute('data-cr-metrica')] = x.textContent.trim(); });
        host.querySelectorAll('[data-cr-grafico]').forEach(function (el) { grafDia(el, datos, b.getAttribute('data-cr-metrica'), t); });
      } else if (panel) {
        panel.close();
      }
    });
    // Al cambiar el ancho, las gráficas con texto se redibujan a su tamaño nuevo.
    var reloj = null, anchoAntes = window.innerWidth;
    window.addEventListener('resize', function () {
      if (window.innerWidth === anchoAntes) return;
      anchoAntes = window.innerWidth;
      clearTimeout(reloj);
      reloj = setTimeout(function () {
        if (pestanaActiva()) dibujar(raiz);
        if (panel && panel.open) dibujar(cuerpo);
      }, 180);
    });
    window.addEventListener('hashchange', navegar);
    window.addEventListener('popstate', navegar);
    window.addEventListener('cr:tab', navegar);
    consumirExpViejo();
    navegar();
  }

  window.CentroResultados = { dibujar: dibujar, trazado: trazado, escala: escala };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
