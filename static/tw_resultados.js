/* «Resultados de tu tienda» (spec 2026-10-08-tw-resultados-de-tu-tienda): la gráfica de la pestaña Triple Whale.
   Lee el JSON que pinta _tw_resultados.html (#tw-resultados-datos) y dibuja en SVG la métrica de la tarjeta
   elegida: barras de gasto (por antigüedad o por canal), línea con área, hoy punteado y aparte, comparación con el
   periodo anterior, tendencia de 7 días, días fuera de lo normal, mejor día, el recuadro de cada día y el detalle
   del día (fragmento del servidor: triple_whale.rutas.ver_dia). ES5, sin librerías, como exp_resultados.js: los
   datos entran solo con textContent/setAttribute; innerHTML solo con el fragmento del servidor (ya escapado por
   Jinja); los colores van por clases (estilos/pantallas/triple-whale.css). Lo puro vive en TwResultados._puro
   (tests/js/tw_resultados.test.mjs). _tab_triple_whale.html llama TwResultados.iniciar(cont) cada vez que pinta
   el panel, porque los <script> de un fragmento que llega por fetch no corren. */
(function () {
  'use strict';
  if (window.TwResultados) return;
  var NS = 'http://www.w3.org/2000/svg';
  var ANCHO = 720, ALTO = 270, M = { izq: 52, der: 16, arriba: 18, abajo: 28 };

  // ---------------------------------------------------------------- puro ---
  function numero(v) { return typeof v === 'number' && isFinite(v); }

  function pasoRedondo(max, marcas) {
    if (!(max > 0)) return 1;
    var bruto = max / (marcas || 4), exp = Math.pow(10, Math.floor(Math.log(bruto) / Math.LN10)), f = bruto / exp;
    var paso = f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10;
    return paso * exp;
  }

  function escala(max) {
    if (!(max > 0)) return { paso: 1, tope: 1 };
    var paso = pasoRedondo(max, 4);
    return { paso: paso, tope: Math.ceil(max / paso - 1e-9) * paso };
  }

  function promedio7(valores, i) {
    var suma = 0, n = 0;
    for (var k = Math.max(0, i - 6); k <= i; k++) {
      if (numero(valores[k])) { suma += valores[k]; n++; }
    }
    return n ? suma / n : null;
  }

  function dividir(a, b) { return b ? a / b : null; }

  function valor(clave, d) {
    if (clave === 'ventas') return d.ing;
    if (clave === 'pedidos') return d.ped;
    if (clave === 'gasto') return d.gas;
    if (clave === 'mer') return dividir(d.ing, d.gas);
    if (clave === 'ticket') return dividir(d.ing, d.ped);
    if (clave === 'cpp') return dividir(d.gas, d.ped);
    if (clave === 'clientes_nuevos') return dividir(d.nc || 0, d.ped);
    return null;
  }

  function posicionAviso(x, ancho, anchoAviso, margen) {
    var izq = x + margen;
    if (izq + anchoAviso > ancho - 4) izq = x - margen - anchoAviso;
    return Math.max(4, izq);
  }

  function indiceEn(px, izq, paso, n) {
    return Math.max(0, Math.min(n - 1, Math.floor((px - izq) / paso)));
  }

  // Números con los separadores de la app (idiomas.numero agrupa también los de 4 cifras: «4.000»).
  function fmt(v, decimales, lang) {
    var s = Math.abs(v).toFixed(decimales), partes = s.split('.');
    var ent = partes[0].replace(/\B(?=(\d{3})+(?!\d))/g, lang === 'en' ? ',' : '.');
    var signo = v < 0 && Number(s) !== 0 ? '-' : '';
    return signo + ent + (partes[1] ? (lang === 'en' ? '.' : ',') + partes[1] : '');
  }
  function dinero(v, moneda, lang) {
    if (!numero(v)) return '—';
    return fmt(v, Math.abs(v) >= 100 || v === Math.round(v) ? 0 : 2, lang) + ' ' + moneda;
  }
  function veces(v, lang) { return numero(v) ? fmt(v, 2, lang) + '×' : '—'; }
  function pct(f, lang) {
    if (!numero(f)) return '—';
    var x = f * 100;
    return fmt(x, Math.abs(x) < 10 && Math.abs(x - Math.round(x)) >= 0.05 ? 1 : 0, lang) + ' %';
  }
  function entero(v, lang) { return numero(v) ? fmt(Math.round(v), 0, lang) : '—'; }
  function texto(plantilla, valores) {
    return String(plantilla || '').replace(/%\((\w+)\)s/g, function (_, k) { return valores[k] !== undefined ? valores[k] : ''; });
  }

  // ------------------------------------------------------------ ayudantes ---
  function svg(tag, attrs, padre, contenido) {
    var el = document.createElementNS(NS, tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    if (contenido !== undefined) el.textContent = contenido;
    if (padre) padre.appendChild(el);
    return el;
  }
  function html(tag, clase, padre, contenido) {
    var el = document.createElement(tag);
    if (clase) el.className = clase;
    if (contenido !== undefined) el.textContent = contenido;
    if (padre) padre.appendChild(el);
    return el;
  }
  function vaciar(el) { while (el.firstChild) el.removeChild(el.firstChild); }
  function fechaDe(iso) { var p = String(iso).split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }
  function capital(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  function iniciar(raiz) {
    var seccion = raiz && raiz.querySelector('[data-twr]');
    var fuente = raiz && raiz.querySelector('#tw-resultados-datos');
    if (!seccion || !fuente || seccion.dataset.twrListo) return;
    var datos;
    try { datos = JSON.parse(fuente.textContent); } catch (e) { return; }
    if (!datos || !datos.dias || !datos.dias.length) return;
    seccion.dataset.twrListo = '1';

    var dias = datos.dias, n = dias.length, T = datos.textos || {};
    var LANG = datos.lang || document.documentElement.lang || 'es';
    var metas = {};
    (datos.metricas || []).forEach(function (m) { metas[m.clave] = m; });
    var st = { metrica: 'ventas', comparar: !!datos.comparar, tendencia: false, modo: 'edad', sel: -1, foco: null,
               pedido: 0 };
    var lienzo = seccion.querySelector('[data-twr-svg]');
    var aviso = seccion.querySelector('[data-twr-aviso]');
    var leyenda = seccion.querySelector('[data-twr-leyenda]');
    var caja = seccion.querySelector('[data-twr-grafico]');
    var modo = seccion.querySelector('[data-twr-modo]');
    var detalle = seccion.querySelector('[data-twr-dia]');
    var geo = null;   // la geometría del último dibujo (para el recuadro y el clic)

    function formatear(clave, v) {
      var formato = (metas[clave] || {}).formato;
      if (formato === 'dinero') return dinero(v, datos.moneda, LANG);
      if (formato === 'veces') return veces(v, LANG);
      if (formato === 'pct') return pct(v, LANG);
      return entero(v, LANG);
    }
    function etiquetaEje(clave, v) {
      var formato = (metas[clave] || {}).formato;
      if (formato === 'veces') return fmt(v, v % 1 ? 1 : 0, LANG) + '×';
      if (formato === 'pct') return fmt(v * 100, 0, LANG) + ' %';
      if (v >= 1e6) return fmt(v / 1e6, v % 1e6 ? 1 : 0, LANG) + ' M';
      if (v >= 1e3) return fmt(v / 1e3, v % 1e3 ? 1 : 0, LANG) + ' k';
      return fmt(v, v % 1 ? 1 : 0, LANG);
    }
    function fechaCorta(iso) {
      try { return fechaDe(iso).toLocaleDateString(LANG, { day: 'numeric', month: 'short' }); } catch (e) { return iso; }
    }
    function fechaLarga(iso) {
      try { return capital(fechaDe(iso).toLocaleDateString(LANG, { weekday: 'short', day: 'numeric', month: 'short' })); }
      catch (e) { return iso; }
    }
    function diaSemana(iso) {
      try { return fechaDe(iso).toLocaleDateString(LANG, { weekday: 'long' }); } catch (e) { return ''; }
    }

    // La serie que se dibuja: los valores del día o su promedio de 7 días (sin hoy, que va a medias).
    function serieDe(lista, clave, conHoy) {
      var crudos = lista.map(function (d) { return valor(clave, d); });
      if (!st.tendencia) return crudos;
      var limite = conHoy ? crudos.length - 1 : crudos.length;
      return crudos.map(function (_, i) { return i < limite ? promedio7(crudos.slice(0, limite), i) : null; });
    }

    function barra(padre, x, yTop, w, h, clase) {
      if (!(h > 0.5)) return;
      var r = Math.min(3, w / 2, h);
      svg('path', { 'class': 'twr-barra ' + clase, d: 'M' + x + ',' + (yTop + h) + ' V' + (yTop + r) + ' Q' + x + ',' + yTop +
        ' ' + (x + r) + ',' + yTop + ' H' + (x + w - r) + ' Q' + (x + w) + ',' + yTop + ' ' + (x + w) + ',' + (yTop + r) +
        ' V' + (yTop + h) + ' Z' }, padre);
    }

    function tramos(valores, xc, y, hasta) {
      var partes = [], actual = [];
      for (var i = 0; i < hasta; i++) {
        if (numero(valores[i])) actual.push(xc(i).toFixed(1) + ',' + y(valores[i]).toFixed(1));
        else if (actual.length) { partes.push(actual); actual = []; }
      }
      if (actual.length) partes.push(actual);
      return partes;
    }

    function dibujar() {
      var clave = st.metrica, esBarras = clave === 'gasto';
      var serie = serieDe(dias, clave, true);
      var previos = st.comparar ? serieDe(datos.previos || [], clave, false) : [];
      var maximo = 0;
      serie.forEach(function (v) { if (numero(v)) maximo = Math.max(maximo, v); });
      previos.forEach(function (v) { if (numero(v)) maximo = Math.max(maximo, v); });
      if (clave === 'ventas') dias.forEach(function (d) { maximo = Math.max(maximo, d.gas); });
      if (clave === 'mer' && numero(datos.meta_roas)) maximo = Math.max(maximo, datos.meta_roas * 1.1);
      var esc = escala(maximo * 1.06);
      var anchoPlot = ANCHO - M.izq - M.der, altoPlot = ALTO - M.arriba - M.abajo, paso = anchoPlot / n;
      var base = M.arriba + altoPlot;
      var xc = function (i) { return M.izq + paso * (i + 0.5); };
      var y = function (v) { return base - (v / esc.tope) * altoPlot; };
      var bw = Math.max(2, Math.min(18, paso * 0.62));
      geo = { paso: paso, xc: xc, y: y, serie: serie, previos: previos };

      vaciar(lienzo);
      var defs = svg('defs', {}, lienzo);
      var grad = svg('linearGradient', { id: 'twr-area', x1: 0, y1: 0, x2: 0, y2: 1 }, defs);
      svg('stop', { offset: '0', 'class': 'twr-area-ini' }, grad);
      svg('stop', { offset: '1', 'class': 'twr-area-fin' }, grad);
      var rayas = svg('pattern', { id: 'twr-rayas', width: 5, height: 5, patternUnits: 'userSpaceOnUse',
                                   patternTransform: 'rotate(45)' }, defs);
      svg('line', { x1: 0, y1: 0, x2: 0, y2: 5, 'class': 'twr-rayas-linea' }, rayas);

      for (var v = 0; v <= esc.tope + 1e-9; v += esc.paso) {
        svg('line', { x1: M.izq, x2: ANCHO - M.der, y1: y(v), y2: y(v), 'class': v ? 'twr-rejilla' : 'twr-base' }, lienzo);
        svg('text', { x: M.izq - 8, y: y(v), 'text-anchor': 'end', 'dominant-baseline': 'middle', 'class': 'twr-eje' },
            lienzo, etiquetaEje(clave, v));
      }
      if (st.sel >= 0) svg('rect', { x: M.izq + paso * st.sel, y: M.arriba, width: paso, height: altoPlot, rx: 3,
                                     'class': 'twr-sel' }, lienzo);

      // Barras: gasto detrás de las ventas, o el gasto partido por antigüedad o por canal.
      if (clave === 'ventas' || esBarras) {
        dias.forEach(function (d, i) {
          var x = xc(i) - bw / 2, hoy = i === n - 1 ? ' twr-barra-hoy' : '';
          if (clave === 'ventas') { barra(lienzo, x, y(d.gas), bw, base - y(d.gas), 'twr-gasto' + hoy); return; }
          if (st.modo === 'canal' && d.can) {
            var acumulado = 0;
            (datos.canales || []).forEach(function (c) {
              var g = d.can[c.clase] || 0;
              if (g <= 0) return;
              var alto = (g / esc.tope) * altoPlot;
              barra(lienzo, x, y(acumulado) - alto, bw, alto - (acumulado ? 1.5 : 0), 'twr-c-' + c.clase + hoy);
              acumulado += g;
            });
            return;
          }
          if (d.nue === null || d.nue === undefined) {
            barra(lienzo, x, y(d.gas), bw, base - y(d.gas), 'twr-desconocida' + hoy);
            return;
          }
          var viejos = Math.max(0, d.gas - d.nue), hViejos = base - y(viejos), hNuevos = (d.nue / esc.tope) * altoPlot;
          barra(lienzo, x, y(viejos), bw, hViejos, 'twr-gasto' + hoy);
          barra(lienzo, x, y(viejos) - hNuevos, bw, hNuevos - (hViejos > 0 ? 1.5 : 0), 'twr-nuevos' + hoy);
        });
      }

      if (previos.length) {
        tramos(previos, xc, y, previos.length).forEach(function (pts) {
          svg('polyline', { points: pts.join(' '), 'class': 'twr-previa' }, lienzo);
        });
      }
      if (clave === 'mer' && numero(datos.meta_roas)) {
        svg('line', { x1: M.izq, x2: ANCHO - M.der, y1: y(datos.meta_roas), y2: y(datos.meta_roas), 'class': 'twr-meta' }, lienzo);
        svg('text', { x: ANCHO - M.der - 2, y: y(datos.meta_roas) - 6, 'text-anchor': 'end', 'class': 'twr-meta-texto' },
            lienzo, texto(T.meta, { x: veces(datos.meta_roas, LANG) }));
      }

      if (!esBarras) {
        var completos = tramos(serie, xc, y, n - 1);
        completos.forEach(function (pts) {
          var primero = pts[0].split(','), ultimo = pts[pts.length - 1].split(',');
          svg('path', { d: 'M' + primero[0] + ',' + base + ' L' + pts.join(' L') + ' L' + ultimo[0] + ',' + base + ' Z',
                        'class': 'twr-area' }, lienzo);
          svg('polyline', { points: pts.join(' '), 'class': 'twr-linea' }, lienzo);
        });
        var hoyV = serie[n - 1], ayerV = serie[n - 2];
        if (!st.tendencia && numero(hoyV)) {
          if (numero(ayerV)) svg('line', { x1: xc(n - 2), y1: y(ayerV), x2: xc(n - 1), y2: y(hoyV), 'class': 'twr-linea-hoy' }, lienzo);
          svg('circle', { cx: xc(n - 1), cy: y(hoyV), r: 4, 'class': 'twr-punto-hoy' }, lienzo);
        }
        if (!st.tendencia) {
          var raros = (datos.raros || {})[clave] || {};
          Object.keys(raros).forEach(function (k) {
            var i = +k;
            if (numero(serie[i])) svg('circle', { cx: xc(i), cy: y(serie[i]), r: 7,
                                                   'class': raros[k] > 0 ? 'twr-raro-arriba' : 'twr-raro-abajo' }, lienzo);
          });
          var mejor = (datos.mejor || {})[clave];
          if (mejor !== null && mejor !== undefined && numero(serie[mejor])) {
            svg('circle', { cx: xc(mejor), cy: y(serie[mejor]), r: 4.5, 'class': 'twr-mejor' }, lienzo);
            svg('text', { x: Math.min(ANCHO - M.der - 30, Math.max(M.izq + 30, xc(mejor))), y: y(serie[mejor]) - 12,
                          'text-anchor': 'middle', 'class': 'twr-mejor-texto' }, lienzo, formatear(clave, serie[mejor]));
          }
        }
      }

      var cada = Math.max(1, Math.ceil(n / 7));
      for (var i = 0; i < n - 1; i++) {
        if ((n - 1 - i) % cada === 0 && n - 1 - i >= Math.max(2, cada / 2)) {
          svg('text', { x: xc(i), y: ALTO - 8, 'text-anchor': 'middle', 'class': 'twr-eje' }, lienzo, fechaCorta(dias[i].f));
        }
      }
      svg('text', { x: xc(n - 1), y: ALTO - 8, 'text-anchor': 'middle', 'class': 'twr-eje twr-eje-hoy' }, lienzo, T.hoy);

      geo.cruz = svg('line', { x1: 0, x2: 0, y1: M.arriba, y2: base, 'class': 'twr-cruz' }, lienzo);
      geo.punto = svg('circle', { r: 5, cx: -10, cy: -10, 'class': 'twr-punto' }, lienzo);
      svg('rect', { x: M.izq, y: M.arriba, width: anchoPlot, height: altoPlot, 'class': 'twr-blanco' }, lienzo);
      var nombre = (metas[clave] || {}).etiqueta || '';
      lienzo.setAttribute('aria-label', texto(T.grafica, { m: nombre }));
      leyendaDe(clave, nombre);
      if (modo) modo.hidden = !esBarras;
    }

    function muestra(clase, etiqueta) {
      var li = html('li', '', leyenda);
      html('i', 'twr-muestra ' + clase, li);
      li.appendChild(document.createTextNode(etiqueta));
    }

    function leyendaDe(clave, nombre) {
      vaciar(leyenda);
      if (clave !== 'gasto') muestra('twr-muestra-linea', st.tendencia ? texto(T.promedio, { m: nombre }) : nombre);
      if (clave === 'ventas') muestra('twr-gasto', T.gasto);
      if (clave === 'gasto' && st.modo === 'canal') {
        (datos.canales || []).forEach(function (c) { muestra('twr-c-' + c.clase, c.nombre); });
      } else if (clave === 'gasto') {
        muestra('twr-nuevos', T.nuevos_leyenda);
        muestra('twr-gasto', T.viejos_leyenda);
        if (dias.some(function (d) { return d.nue === null || d.nue === undefined; })) muestra('twr-desconocida', T.desconocida);
      }
      if (st.comparar) muestra('twr-muestra-previa', T.previo);
      var raros = (datos.raros || {})[clave] || {};
      if (clave !== 'gasto' && !st.tendencia && Object.keys(raros).length) muestra('twr-muestra-raro', T.raro);
    }

    // ------------------------------------------------------------ recuadro ---
    function fila(padre, etiqueta, valorTexto, claseMuestra) {
      var f = html('div', 'twr-aviso-fila', padre);
      var e = html('span', '', f);
      if (claseMuestra) html('i', 'twr-muestra twr-muestra-corta ' + claseMuestra, e);
      e.appendChild(document.createTextNode(etiqueta));
      html('b', '', f, valorTexto);
    }

    function mostrar(i) {
      if (!geo) return;
      var d = dias[i], hoy = i === n - 1, clave = st.metrica;
      geo.cruz.setAttribute('x1', geo.xc(i));
      geo.cruz.setAttribute('x2', geo.xc(i));
      geo.cruz.classList.add('twr-visible');
      if (clave !== 'gasto' && numero(geo.serie[i])) {
        geo.punto.setAttribute('cx', geo.xc(i));
        geo.punto.setAttribute('cy', geo.y(geo.serie[i]));
        geo.punto.classList.add('twr-visible');
      } else {
        geo.punto.classList.remove('twr-visible');
      }
      vaciar(aviso);
      html('div', 'twr-aviso-fecha', aviso, fechaLarga(d.f) + (hoy ? ' · ' + T.hoy_medias : ''));
      if (['ticket', 'cpp', 'clientes_nuevos'].indexOf(clave) >= 0) {
        fila(aviso, (metas[clave] || {}).etiqueta || '', formatear(clave, valor(clave, d)), 'twr-muestra-linea');
      }
      fila(aviso, T.ventas, dinero(d.ing, datos.moneda, LANG), 'twr-muestra-linea');
      fila(aviso, T.gasto, dinero(d.gas, datos.moneda, LANG), 'twr-gasto');
      if (clave === 'gasto' && st.modo === 'canal' && d.can) {
        (datos.canales || []).forEach(function (c) {
          if (d.can[c.clase]) fila(aviso, c.nombre, dinero(d.can[c.clase], datos.moneda, LANG), 'twr-c-' + c.clase);
        });
      }
      fila(aviso, T.retorno, veces(valor('mer', d), LANG));
      fila(aviso, T.pedidos, entero(d.ped, LANG));
      fila(aviso, T.nuevos, d.nue === null || d.nue === undefined || !d.gas ? '—' : pct(d.nue / d.gas, LANG), 'twr-nuevos');
      var raro = st.tendencia ? undefined : ((datos.raros || {})[clave] || {})[i];
      if (raro !== undefined) {
        html('div', 'twr-aviso-sep', aviso);
        html('div', 'twr-aviso-nota ' + (raro > 0 ? 'twr-bueno' : 'twr-malo'), aviso,
             (raro > 0 ? '▲ ' : '▼ ') + texto(raro > 0 ? T.sobre : T.bajo, { pct: pct(Math.abs(raro), LANG), dia: diaSemana(d.f) }));
      }
      var previo = st.comparar ? (datos.previos || [])[i] : null;
      if (previo) {
        html('div', 'twr-aviso-sep', aviso);
        fila(aviso, texto(T.antes, { dia: fechaLarga(previo.f) }), formatear(clave, numero(geo.previos[i]) ? geo.previos[i] : valor(clave, previo)));
      }
      if (!hoy) html('div', 'twr-aviso-pista', aviso, T.pista);
      aviso.hidden = false;
      var rLienzo = lienzo.getBoundingClientRect(), rCaja = caja.getBoundingClientRect();
      var escalaX = rLienzo.width / ANCHO;
      var x = geo.xc(i) * escalaX + (rLienzo.left - rCaja.left);
      aviso.style.left = posicionAviso(x, rCaja.width, aviso.offsetWidth, 14) + 'px';
      aviso.style.top = (rLienzo.top - rCaja.top + 8) + 'px';
    }

    function ocultar() {
      aviso.hidden = true;
      if (geo) { geo.cruz.classList.remove('twr-visible'); geo.punto.classList.remove('twr-visible'); }
    }

    function indiceDe(ev) {
      var r = lienzo.getBoundingClientRect();
      if (!r.width || !geo) return null;
      return indiceEn((ev.clientX - r.left) * ANCHO / r.width, M.izq, geo.paso, n);
    }

    // ------------------------------------------------------- detalle del día ---
    function abrir(fecha, conFoco) {
      if (!fecha) return;
      var i = -1;
      for (var k = 0; k < n; k++) if (dias[k].f === fecha) i = k;
      if (i === n - 1) return;                       // hoy va a medias: no tiene detalle
      st.sel = i;
      dibujar();
      var mio = ++st.pedido;
      vaciar(detalle);
      html('p', 'twr-nota', detalle, T.cargando);
      var url = datos.url_dia || '';
      url += (url.indexOf('?') >= 0 ? '&' : '?') + 'fecha=' + encodeURIComponent(fecha);
      fetch(url, { headers: { 'X-Requested-With': 'fetch' } })
        .then(function (r) { return r.ok ? r.text() : Promise.reject(r.status); })
        .then(function (fragmento) {
          if (mio !== st.pedido) return;
          detalle.innerHTML = fragmento;
          if (conFoco) detalle.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        })
        .catch(function () {
          if (mio !== st.pedido) return;
          vaciar(detalle);
          html('p', 'twr-nota', detalle, T.error_dia);
        });
    }

    // ---------------------------------------------------------- minigráficas ---
    seccion.querySelectorAll('[data-twr-spark]').forEach(function (s) {
      var clave = s.getAttribute('data-twr-spark');
      var valores = dias.slice(0, n - 1).map(function (d) { return valor(clave, d); });
      var nums = valores.filter(numero);
      if (nums.length < 2) return;
      var max = Math.max.apply(null, nums), min = Math.min.apply(null, nums), rango = max - min || 1;
      var pts = [];
      valores.forEach(function (v, i) {
        if (numero(v)) pts.push((i / Math.max(1, valores.length - 1) * 100).toFixed(1) + ',' + (25 - (v - min) / rango * 22).toFixed(1));
      });
      vaciar(s);
      svg('polyline', { points: pts.join(' '), 'class': 'twr-spark-linea' }, s);
    });

    // -------------------------------------------------------------- eventos ---
    seccion.addEventListener('click', function (ev) {
      var t = ev.target.closest('[data-twr-metrica]');
      if (t) {
        st.metrica = t.getAttribute('data-twr-metrica');
        seccion.querySelectorAll('[data-twr-metrica]').forEach(function (b) {
          b.setAttribute('aria-selected', b === t ? 'true' : 'false');
        });
        ocultar();
        dibujar();
        return;
      }
      var m = ev.target.closest('[data-twr-modo-valor]');
      if (m) {
        st.modo = m.getAttribute('data-twr-modo-valor');
        seccion.querySelectorAll('[data-twr-modo-valor]').forEach(function (b) {
          b.setAttribute('aria-pressed', b === m ? 'true' : 'false');
        });
        dibujar();
        return;
      }
      var dia = ev.target.closest('[data-twr-dia]');
      if (dia) { ev.preventDefault(); abrir(dia.getAttribute('data-twr-dia'), true); return; }
      var ir = ev.target.closest('[data-twr-ir]');
      if (ir) {
        var destino = document.getElementById(ir.getAttribute('data-twr-ir'));
        if (destino) { ev.preventDefault(); destino.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
      }
    });
    seccion.addEventListener('change', function (ev) {
      if (ev.target.matches('[data-twr-comparar]')) { st.comparar = ev.target.checked; dibujar(); }
      if (ev.target.matches('[data-twr-tendencia]')) { st.tendencia = ev.target.checked; ocultar(); dibujar(); }
    });
    lienzo.addEventListener('pointermove', function (ev) { var i = indiceDe(ev); if (i !== null) mostrar(i); });
    lienzo.addEventListener('pointerdown', function (ev) {
      if (ev.pointerType !== 'mouse') { var i = indiceDe(ev); if (i !== null) mostrar(i); }
    });
    lienzo.addEventListener('pointerleave', function () { if (st.foco === null) ocultar(); });
    lienzo.addEventListener('click', function (ev) {
      var i = indiceDe(ev);
      if (i !== null && i < n - 1) abrir(dias[i].f, true);
    });
    lienzo.addEventListener('keydown', function (ev) {
      var i = st.foco === null ? (st.sel >= 0 ? st.sel : n - 2) : st.foco;
      if (ev.key === 'ArrowLeft') i = Math.max(0, i - 1);
      else if (ev.key === 'ArrowRight') i = Math.min(n - 1, i + 1);
      else if (ev.key === 'Home') i = 0;
      else if (ev.key === 'End') i = n - 1;
      else if (ev.key === 'Enter' || ev.key === ' ') { if (i < n - 1) abrir(dias[i].f, true); ev.preventDefault(); return; }
      else if (ev.key === 'Escape') { st.foco = null; ocultar(); return; }
      else return;
      ev.preventDefault();
      st.foco = i;
      mostrar(i);
    });
    lienzo.addEventListener('blur', function () { st.foco = null; ocultar(); });
    window.addEventListener('resize', ocultar);

    dibujar();
    abrir(datos.dia_inicial, false);
  }

  window.TwResultados = {
    iniciar: iniciar,
    _puro: { pasoRedondo: pasoRedondo, escala: escala, promedio7: promedio7, valor: valor, posicionAviso: posicionAviso,
             indiceEn: indiceEn, dinero: dinero, veces: veces, pct: pct, texto: texto }
  };
  // Si el panel llegó antes que este archivo (va con defer), se inicia aquí; `data-twr-listo` evita hacerlo dos veces.
  if (document.getElementById) {
    var panel = document.getElementById('tw-panel');
    if (panel) iniciar(panel);
  }
})();
