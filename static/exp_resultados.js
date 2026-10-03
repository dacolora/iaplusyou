/* Centro de resultados: GET, SVG y navegación. Textos siempre desde la plantilla. */
(function () {
  'use strict';
  if (window.CentroResultados) return;
  var NS = 'http://www.w3.org/2000/svg';
  function numero(v) { return typeof v === 'number' && isFinite(v); }
  function lista(v) { return Array.isArray(v) ? v : []; }
  function json(s, defecto) { try { return JSON.parse(s); } catch (e) { return defecto; } }
  function vaciar(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function svg(tag, attrs, padre, texto) {
    var el = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    if (texto !== undefined) el.textContent = texto;
    if (padre) padre.appendChild(el);
    return el;
  }
  function formato(v) {
    return numero(v) ? v.toLocaleString(document.documentElement.lang || 'en', { maximumSignificantDigits: 4 }) : '—';
  }
  function escala(valores) {
    var max = 0;
    valores.forEach(function (v) { if (numero(v)) max = Math.max(max, v); });
    if (!max) return 1;
    var potencia = Math.pow(10, Math.floor(Math.log(max) / Math.LN10));
    return Math.ceil(max / potencia) * potencia;
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
  function preparar(el, w, h) {
    var lienzo = el.tagName.toLowerCase() === 'svg' ? el : null;
    vaciar(el);
    if (!lienzo) lienzo = svg('svg', {}, el);
    lienzo.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    lienzo.setAttribute('width', '100%');
    lienzo.setAttribute('role', 'img');
    return lienzo;
  }
  function aviso(punto, host, texto) {
    svg('title', {}, punto, texto);
    punto.setAttribute('tabindex', '0');
    punto.setAttribute('aria-label', texto);
    function mostrar() {
      var caja = host.tagName.toLowerCase() === 'svg' ? host.parentNode : host;
      if (!caja) return;
      var tip = caja.querySelector('.cr-aviso');
      if (!tip) { tip = document.createElement('div'); tip.className = 'cr-aviso'; caja.appendChild(tip); }
      tip.textContent = texto;
      tip.hidden = false;
      caja.style.position = 'relative';
      tip.style.position = 'absolute';
      var r = punto.getBoundingClientRect(), c = caja.getBoundingClientRect();
      tip.style.left = Math.max(0, Math.min(r.left - c.left, c.width - tip.offsetWidth)) + 'px';
      tip.style.top = Math.max(0, r.top - c.top - tip.offsetHeight) + 'px';
    }
    function ocultar() {
      var caja = host.tagName.toLowerCase() === 'svg' ? host.parentNode : host;
      var tip = caja && caja.querySelector('.cr-aviso');
      if (tip) tip.hidden = true;
    }
    punto.addEventListener('pointerenter', mostrar);
    punto.addEventListener('pointerdown', mostrar);
    punto.addEventListener('focus', mostrar);
    punto.addEventListener('pointerleave', ocultar);
    punto.addEventListener('blur', ocultar);
  }
  function linea(el, valores, promedio, escalones, etiquetas) {
    valores = lista(valores); promedio = lista(promedio);
    var s = preparar(el, 240, 72), max = escala(valores.concat(promedio));
    var n = Math.max(valores.length, promedio.length);
    var x = function (i) { return n < 2 ? 120 : 5 + i * 230 / (n - 1); };
    var y = function (v) { return 62 - Math.max(0, v) / max * 55; };
    [promedio, valores].forEach(function (vs, j) {
      svg('path', { d: trazado(vs, x, y, escalones), fill: 'none', 'stroke-width': 2,
        'class': j ? 'cr-linea' : 'cr-promedio', stroke: 'currentColor', 'stroke-dasharray': j ? 'none' : '4 4' }, s);
    });
    valores.forEach(function (v, i) {
      if (!numero(v)) return;
      var p = svg('circle', { cx: x(i), cy: y(v), r: 2.5, 'class': 'cr-punto', fill: 'currentColor' }, s);
      aviso(p, el, (etiquetas && etiquetas[i] ? etiquetas[i] + ' · ' : '') + formato(v));
    });
  }
  function dona(el, datos, porcentaje) {
    var s = preparar(el, 100, 100), valores = porcentaje ? [Math.max(0, Math.min(100, numero(datos) ? datos : 0))] : lista(datos).map(function (v) { return numero(v) ? v : v.valor !== undefined ? v.valor : v.impresiones; });
    var total = porcentaje ? 100 : valores.reduce(function (a, v) { return a + (numero(v) ? Math.max(0, v) : 0); }, 0);
    var largo = 2 * Math.PI * 38, inicio = 0;
    svg('circle', { cx: 50, cy: 50, r: 38, fill: 'none', stroke: 'currentColor', 'class': 'cr-dona-fondo', 'stroke-width': 12, opacity: 0.15 }, s);
    if (!total) return;
    valores.forEach(function (v, i) {
      if (!numero(v) || v <= 0) return;
      var parte = v / total * largo;
      var c = svg('circle', { cx: 50, cy: 50, r: 38, fill: 'none', stroke: 'currentColor', 'stroke-width': 12,
        'class': 'cr-dona-segmento cr-serie-' + (i % 6), 'stroke-dasharray': parte + ' ' + (largo - parte),
        'stroke-dashoffset': -inicio, transform: 'rotate(-90 50 50)' }, s);
      var item = lista(datos)[i];
      aviso(c, el, (item && (item.etiqueta || item.nombre || item.valor_texto) || '') + ' ' + formato(v / total * 100) + '%');
      inicio += parte;
    });
  }
  function dia(el, datos, metrica, textos) {
    var serie = datos.serie || datos, dias = lista(serie.dias), gastos = lista(serie.gasto), valores = lista(serie[metrica]);
    var s = preparar(el, 720, 260), maxG = escala(gastos), maxV = escala(valores), n = dias.length;
    var x = function (i) { return 64 + (i + 0.5) * 592 / Math.max(1, n); };
    var yG = function (v) { return 216 - Math.max(0, v) / maxG * 178; };
    var yV = function (v) { return 216 - Math.max(0, v) / maxV * 178; };
    var etiqueta = textos[metrica] || metrica.toUpperCase(), gasto = textos.gasto || serie.moneda || '';
    s.setAttribute('aria-label', gasto + ' · ' + etiqueta);
    svg('text', { x: 64, y: 16, 'class': 'cr-eje' }, s, gasto + (textos.gasto && serie.moneda ? ' · ' + serie.moneda : ''));
    svg('text', { x: 656, y: 16, 'text-anchor': 'end', 'class': 'cr-eje' }, s, etiqueta);
    for (var i = 0; i <= 4; i++) {
      var yy = 216 - i * 178 / 4;
      svg('line', { x1: 64, x2: 656, y1: yy, y2: yy, 'class': 'cr-rejilla', stroke: 'currentColor', opacity: 0.15 }, s);
      svg('text', { x: 58, y: yy + 4, 'text-anchor': 'end', 'class': 'cr-eje' }, s, formato(i * maxG / 4));
      svg('text', { x: 662, y: yy + 4, 'class': 'cr-eje' }, s, formato(i * maxV / 4));
    }
    dias.forEach(function (d, j) {
      var g = gastos[j], v = valores[j];
      if (numero(g)) {
        var b = svg('rect', { x: x(j) - 220 / Math.max(n, 1), y: yG(g), width: 440 / Math.max(n, 1), height: 216 - yG(g), 'class': 'cr-barra', fill: 'currentColor', opacity: 0.25 }, s);
        aviso(b, el, d + ' · ' + gasto + ': ' + formato(g));
      }
      if (numero(v)) {
        var p = svg('circle', { cx: x(j), cy: yV(v), r: 3, 'class': 'cr-punto', fill: 'currentColor' }, s);
        aviso(p, el, d + ' · ' + etiqueta + ': ' + formato(v));
      }
      if (j % Math.max(5, Math.ceil(n / 7)) === 0 || j === n - 1) svg('text', { x: x(j), y: 244, 'text-anchor': 'middle', 'class': 'cr-eje' }, s, String(d).slice(5));
    });
    svg('path', { d: trazado(valores.slice(0, n), x, yV, false), fill: 'none', stroke: 'currentColor', 'stroke-width': 2, 'class': 'cr-linea', 'pointer-events': 'none' }, s);
    lista(datos.marcas).forEach(function (m) {
      var j = dias.indexOf(m.dia);
      if (j < 0) return;
      var l = svg('line', { x1: x(j), x2: x(j), y1: 30, y2: 216, stroke: 'currentColor', 'stroke-dasharray': '3 4', 'class': 'cr-marca' }, s);
      aviso(l, el, m.dia + ' · ' + m.texto);
    });
  }
  function dibujar(raiz) {
    var bloque = raiz.querySelector('#cr-datos, .cr-datos-pieza');
    var datos = bloque ? json(bloque.textContent, {}) : {};
    var textos = datos.textos || json(raiz.dataset.crTextos || '{}', {});
    raiz.querySelectorAll('[data-cr-metrica]').forEach(function (b) { textos[b.dataset.crMetrica] = b.textContent.trim(); });
    raiz.querySelectorAll('[data-cr-grafico]').forEach(function (el) { dia(el, datos, el.dataset.metrica || 'ctr', textos); });
    raiz.querySelectorAll('[data-cr-spark]').forEach(function (el) { linea(el, json(el.dataset.crSpark, [])); });
    raiz.querySelectorAll('[data-cr-evolucion]').forEach(function (el) { var d = json(el.dataset.crEvolucion, {}); linea(el, d.serie, d.promedio); });
    raiz.querySelectorAll('[data-cr-dona]').forEach(function (el) { dona(el, json(el.dataset.crDona, []), false); });
    raiz.querySelectorAll('[data-cr-dona-pct]').forEach(function (el) { dona(el, json(el.dataset.crDonaPct, null), true); });
    raiz.querySelectorAll('[data-cr-curva]').forEach(function (el) {
      var d = lista(json(el.dataset.crCurva, []));
      linea(el, d.map(function (v) { return Array.isArray(v) ? v[1] : v; }), [], true, d.map(function (v) { return Array.isArray(v) ? v[0] : ''; }));
    });
  }
  function iniciar() {
    var raiz = document.getElementById('cr-resultados');
    if (!raiz || raiz.dataset.crIniciado) return;
    raiz.dataset.crIniciado = '1';
    var pedido = 0, ultima = null, panelPedido = 0, foco;
    var panel = document.getElementById('cr-panel'), cuerpo = panel && panel.querySelector('.cr-panel-cuerpo');
    var textos = json(raiz.dataset.crTextos || '{}', {}), base = window.T_BASE || {};
    function texto(k, respaldo) { return textos[k] || raiz.dataset[k] || base[respaldo] || ''; }
    function estado(host, mensaje, reintentar) {
      vaciar(host);
      var p = document.createElement('p'); p.className = 'estado-vacio'; p.textContent = mensaje; host.appendChild(p);
      if (reintentar) { var b = document.createElement('button'); b.type = 'button'; b.textContent = texto('reintentar', 'recargarAhora'); b.addEventListener('click', reintentar); host.appendChild(b); }
    }
    function pedir(url) { return fetch(url, { headers: { 'X-Requested-With': 'fetch' }, cache: 'no-store' }).then(function (r) { if (!r.ok) throw new Error(String(r.status)); return r.text(); }); }
    function cargar(query, forzar) {
      if (!forzar && ultima === query) return;
      ultima = query;
      var n = ++pedido;
      raiz.setAttribute('aria-busy', 'true');
      estado(raiz, texto('cargando', 'cargando'));
      pedir(raiz.dataset.url + (query ? '?' + query : '')).then(function (html) {
        if (n !== pedido) return;
        raiz.innerHTML = html; // Fragmento HTML de la ruta del proyecto; datos de gráficas por textContent.
        dibujar(raiz);
        if (window.arrancarSondeos) window.arrancarSondeos(raiz);
        raiz.setAttribute('aria-busy', 'false');
      }).catch(function () {
        if (n !== pedido) return;
        raiz.setAttribute('aria-busy', 'false');
        estado(raiz, texto('errorResultados', 'conexionPerdida'), function () { cargar(query, true); });
      });
    }
    function navegar() {
      var nombre = location.hash.slice(1).split('?')[0];
      var tab = document.getElementById('tab-experimentos');
      if (['experimentos', 'tablero', 'ads'].indexOf(nombre) < 0 && !(tab && tab.classList.contains('activo'))) {
        pedido++; ultima = null; return;
      }
      var query = new URLSearchParams(location.hash.indexOf('?') < 0 ? '' : location.hash.slice(location.hash.indexOf('?') + 1));
      var exp = new URLSearchParams(location.search).get('exp');
      if (!query.has('exp') && exp) query.set('exp', exp);
      if (query.has('piezas') && raiz.dataset.urlNuevo) { location.replace(raiz.dataset.urlNuevo + '?piezas=' + encodeURIComponent(query.get('piezas'))); return; }
      cargar(query.toString());
    }
    function abrir(url, origen) {
      if (!panel || !cuerpo) return;
      foco = origen;
      var n = ++panelPedido;
      if (!panel.open) panel.showModal();
      estado(cuerpo, texto('cargando', 'cargando'));
      pedir(url).then(function (html) {
        if (n !== panelPedido || !panel.open) return;
        cuerpo.innerHTML = html;
        dibujar(cuerpo);
        if (window.arrancarSondeos) window.arrancarSondeos(cuerpo);
      }).catch(function (err) {
        if (n !== panelPedido || !panel.open) return;
        estado(cuerpo, texto(err.message === '404' ? 'piezaNoExiste' : 'errorPieza', err.message === '404' ? 'detalleNoExiste' : 'detalleNoCargo'), function () { abrir(url, origen); });
      });
    }
    if (panel) panel.addEventListener('close', function () { panelPedido++; cuerpo.querySelectorAll('video, audio').forEach(function (v) { v.pause(); }); if (foco && foco.isConnected) foco.focus(); });
    document.addEventListener('click', function (ev) {
      if (!ev.target.closest) return;
      var b = ev.target.closest('[data-cr-filtro], [data-cr-pieza], [data-cr-metrica], .cr-panel-cerrar');
      if (!b || (!raiz.contains(b) && !(panel && panel.contains(b)))) return;
      if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.altKey || ev.button > 0) return;
      if (b.hasAttribute('data-cr-pieza') && ev.target.closest('a, button, input, select, form') && ev.target.closest('a, button, input, select, form') !== b) return;
      ev.preventDefault();
      if (b.hasAttribute('data-cr-filtro')) { history.pushState(null, '', b.getAttribute('href')); window.dispatchEvent(new Event('hashchange')); }
      else if (b.hasAttribute('data-cr-pieza')) abrir(b.dataset.crPieza, b);
      else if (b.hasAttribute('data-cr-metrica')) {
        var host = panel && panel.contains(b) ? cuerpo : raiz;
        host.querySelectorAll('[data-cr-metrica]').forEach(function (otro) { otro.setAttribute('aria-pressed', String(otro === b)); otro.classList.toggle('activo', otro === b); });
        host.querySelectorAll('[data-cr-grafico]').forEach(function (el) { el.dataset.metrica = b.dataset.crMetrica; });
        dibujar(host);
      } else panel.close();
    });
    document.addEventListener('keydown', function (ev) {
      var b = ev.target.closest && ev.target.closest('[data-cr-pieza]');
      if (b && b.tagName === 'TR' && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); abrir(b.dataset.crPieza, b); }
    });
    window.addEventListener('hashchange', navegar);
    window.addEventListener('popstate', navegar);
    window.addEventListener('cr:tab', navegar);
    navegar();
  }
  window.CentroResultados = { dibujar: dibujar, trazado: trazado, escala: escala };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', iniciar); else iniciar();
})();
