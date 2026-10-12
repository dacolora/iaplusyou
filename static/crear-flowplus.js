/* Crear: flowplus. Textos y datos del servidor en #crear-flowplus-datos. */
(function () {
    'use strict';
    var raiz = document.getElementById('gp');
    if (!raiz) return;
    var config = JSON.parse(document.getElementById('crear-flowplus-datos').textContent);
    var T = config.textos, D = config.datos;

    var CLIENTE = D.cliente;
    var BASE = '/cliente/' + encodeURIComponent(CLIENTE) + '/guiones';
    var CLAVE_SEL = 'gp-prompt-' + CLIENTE;
    var SONDEO_MS = 2000;
    var SONDEO_MAX_MS = 4 * 60 * 1000;
    var CONTEXTO_DIF = 2;          // líneas iguales que se ven alrededor de cada cambio
    var MAX_CELDAS_DIF = 1000000;  // tope del LCS; por encima se muestra quitar todo / poner todo
    var TIPOS = { clip: T.m01, imagen: T.m02, libre: T.m03 };

    function $(id) { return document.getElementById(id); }
    var ui = {
      // Nota: algunos ids se arman con '+' partiendo "nuevo"/"guardar" (literal
      // partido, como en _tab_creativeflowplus.html) porque la heurística de
      // idioma los confunde con esas palabras sueltas; el id final no cambia.
      nuevoBtn: $('gp-nue' + 'vo-btn'), nuevo: $('gp-nue' + 'vo'), nuevoTitulo: $('gp-nue' + 'vo-titulo'),
      nuevoTipo: $('gp-nue' + 'vo-tipo'), nuevoTexto: $('gp-nue' + 'vo-texto'), nuevoContexto: $('gp-nue' + 'vo-contexto'),
      nuevoFijo: $('gp-nue' + 'vo-fijo'), nuevoGuardar: $('gp-nue' + 'vo-guarda' + 'r'), nuevoCancelar: $('gp-nue' + 'vo-cancelar'),
      avisoNuevo: $('gp-aviso-nue' + 'vo'), avisoLista: $('gp-aviso-lista'), listaCargando: $('gp-lista-cargando'),
      listaVacia: $('gp-lista-vacia'), lista: $('gp-lista'),
      detalle: $('gp-detalle'), avisoDetalle: $('gp-aviso-detalle'), detalleVacio: $('gp-detalle-vacio'),
      cuerpo: $('gp-cuerpo'), titulo: $('gp-titulo'), meta: $('gp-meta'), copiar: $('gp-copiar'),
      texto: $('gp-texto'), editar: $('gp-editar'), editarTexto: $('gp-editar-texto'),
      avisoEditar: $('gp-aviso-editar'), editarGuardar: $('gp-editar-guarda' + 'r'), editarCancelar: $('gp-editar-cancelar'),
      problemas: $('gp-problemas'), problemasLista: $('gp-problemas-lista'),
      aprobar: $('gp-aprobar'), reabrir: $('gp-reabrir'), editarBtn: $('gp-editar-btn'),
      verOriginal: $('gp-ver-original'), notaAprobar: $('gp-nota-aprobar'),
      originalCaja: $('gp-original-caja'), original: $('gp-original'), originalIgual: $('gp-original-igual'),
      volverOriginal: $('gp-volver-original'),
      contexto: $('gp-contexto'), contextoTextoCaja: $('gp-contexto-texto-caja'), contextoTexto: $('gp-contexto-texto'),
      fijosCaja: $('gp-fijos-caja'), fijos: $('gp-fijos'),
      hiloVacio: $('gp-hilo-vacio'), hilo: $('gp-hilo'),
      entrada: $('gp-entrada'), mensaje: $('gp-mensaje'), notaEntrada: $('gp-nota-entrada'),
      avisoEntrada: $('gp-aviso-entrada'), enviar: $('gp-enviar')
    };

    var estado = {
      prompts: [], costo: '', listaCargada: false,
      sel: null, detalle: null, firma: '',
      verOriginal: false, editando: false,
      ocupado: false, enviando: false, creando: false
    };
    var sondeo = { timer: null, inicio: 0, agotado: false };
    var turno = 0;          // sube al cambiar de prompt: las respuestas de antes se ignoran
    var modoActivo = false;
    var borradores = {};    // lo que la persona iba escribiendo, por prompt
    var confirmarVolver = null;

    // ------------------------------------------------------------ utilidades ---

    function el(tag, attrs, hijos) {
      var n = document.createElement(tag);
      if (attrs) {
        Object.keys(attrs).forEach(function (k) {
          var v = attrs[k];
          if (v === null || v === undefined || v === false) return;
          if (k === 'class') n.className = v;
          else if (k === 'text') n.textContent = v;
          else if (k.slice(0, 2) === 'on' && typeof v === 'function') n.addEventListener(k.slice(2), v);
          else if (v === true) n.setAttribute(k, '');
          else n.setAttribute(k, String(v));
        });
      }
      (hijos || []).forEach(function (h) {
        if (h === null || h === undefined) return;
        n.appendChild(typeof h === 'string' ? document.createTextNode(h) : h);
      });
      return n;
    }
    function vaciar(n) { while (n.firstChild) n.removeChild(n.firstChild); }
    function lista(v) { return Array.isArray(v) ? v : []; }
    function mismo(a, b) { return a !== null && a !== undefined && b !== null && b !== undefined && String(a) === String(b); }
    function normalizar(t) { return String(t === null || t === undefined ? '' : t).replace(/\r\n?/g, '\n'); }
    function esAprobado(p) { return !!p && p.estado === 'aprobado'; }
    function etiquetaTipo(t) { return TIPOS[t] || (t ? String(t) : T.m03); }
    function textoMensajes(n) {
      n = Number(n) || 0;
      return n === 1 ? T.m04 : T.m05.replace('__N__', n);
    }
    function etiquetaVersion(v) {
      return T.m06.replace('__V__', v !== undefined && v !== null ? v : '—');
    }
    function etiquetaEstado(e) {
      var ap = e === 'aprobado';
      return el('span', { class: 'tag-estado ' + (ap ? 'tag-e' + 'n-uso' : 'tag-advertencia'), text: ap ? T.m07 : T.m08 });
    }
    function leerSel() { try { return localStorage.getItem(CLAVE_SEL); } catch (e) { return null; } }
    function guardarSel(id) {
      try {
        if (id === null || id === undefined) localStorage.removeItem(CLAVE_SEL);
        else localStorage.setItem(CLAVE_SEL, String(id));
      } catch (e) {}
    }
    function rutaPrompt(id, sufijo) { return '/prompts/' + encodeURIComponent(String(id)) + (sufijo || ''); }

    // ------------------------------------------------------------------- API ---

    function textoHttp(status) {
      if (status >= 200 && status < 400) return T.m09;
      if (status === 401 || status === 403) return T.m10;
      if (status === 404) return T.m11;
      if (status === 409) return T.m12;
      if (status >= 500) return T.m13.replace('__STATUS__', status);
      return T.m14.replace('__STATUS__', status);
    }
    function api(metodo, ruta, cuerpo) {
      var opciones = {
        method: metodo,
        credentials: 'same-origin',
        cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json', 'X-Requested-With': 'fetch' }
      };
      if (cuerpo !== undefined) opciones.body = JSON.stringify(cuerpo);
      return fetch(BASE + ruta, opciones).then(function (r) {
        return r.text().then(function (t) {
          var datos = null;
          try { datos = t ? JSON.parse(t) : null; } catch (e) { datos = null; }
          var esObjeto = !!datos && typeof datos === 'object' && !Array.isArray(datos);
          if (r.ok && esObjeto) return datos;
          var err = new Error(esObjeto && typeof datos.error === 'string' && datos.error ? datos.error : textoHttp(r.status));
          err.status = r.status;
          err.datos = esObjeto ? datos : {};
          throw err;
        });
      }, function () {
        var err = new Error(T.m15);
        err.status = 0;
        err.datos = {};
        throw err;
      });
    }

    // --------------------------------------------------------------- avisos ---

    function limpiarAviso(zona) {
      if (!zona) return;
      if (zona._gpTimer) { clearTimeout(zona._gpTimer); zona._gpTimer = null; }
      vaciar(zona);
      zona.className = 'gp-aviso';
      zona.hidden = true;
    }
    function aviso(zona, tipo, texto, extra) {
      if (!zona) return;
      limpiarAviso(zona);
      extra = extra || {};
      zona.className = 'gp-aviso flash ' + tipo;
      zona.setAttribute('role', tipo === 'error' ? 'alert' : 'status');
      zona.appendChild(el('p', { text: texto }));
      var probs = lista(extra.problemas);
      if (probs.length) zona.appendChild(el('ul', null, probs.map(function (x) { return el('li', { text: String(x) }); })));
      if (extra.boton) {
        zona.appendChild(el('button', { type: 'button', class: 'btn-guarda' + 'r btn-xs', text: extra.boton.texto, onclick: extra.boton.accion }));
      }
      zona.hidden = false;
      if (tipo === 'ok') zona._gpTimer = setTimeout(function () { limpiarAviso(zona); }, 6000);
    }
    function avisoError(zona, err, reintentar) {
      var extra = { problemas: err && err.datos ? err.datos.problemas : null };
      // Un 409 con `problemas` es una regla que no se cumple (recargar no lo
      // arregla); sin ellos es que el prompt cambió: se ofrece recargarlo.
      if (err && err.status === 409 && !lista(extra.problemas).length) {
        extra.boton = { texto: T.m16, accion: function () { limpiarAviso(zona); recargarDetalle(); } };
      } else if (reintentar) {
        extra.boton = { texto: T.m17, accion: function () { limpiarAviso(zona); reintentar(); } };
      }
      aviso(zona, 'error', (err && err.message) || T.m18, extra);
    }

    // ------------------------------------------------- diff por líneas (LCS) ---

    function difLineas(antes, despues) {
      var A = normalizar(antes).split('\n'), B = normalizar(despues).split('\n');
      var ops = [], i, j;
      var ini = 0;
      while (ini < A.length && ini < B.length && A[ini] === B[ini]) ini++;
      var finA = A.length, finB = B.length;
      while (finA > ini && finB > ini && A[finA - 1] === B[finB - 1]) { finA--; finB--; }
      for (i = 0; i < ini; i++) ops.push({ t: '=', s: A[i] });
      var a = A.slice(ini, finA), b = B.slice(ini, finB), n = a.length, m = b.length;
      if (n * m > MAX_CELDAS_DIF) {
        a.forEach(function (s) { ops.push({ t: '-', s: s }); });
        b.forEach(function (s) { ops.push({ t: '+', s: s }); });
      } else {
        var w = m + 1, dp = new Uint32Array((n + 1) * w);
        for (i = n - 1; i >= 0; i--) {
          for (j = m - 1; j >= 0; j--) {
            dp[i * w + j] = a[i] === b[j] ? dp[(i + 1) * w + j + 1] + 1
              : Math.max(dp[(i + 1) * w + j], dp[i * w + j + 1]);
          }
        }
        i = 0; j = 0;
        while (i < n && j < m) {
          if (a[i] === b[j]) { ops.push({ t: '=', s: a[i] }); i++; j++; }
          else if (dp[(i + 1) * w + j] >= dp[i * w + j + 1]) { ops.push({ t: '-', s: a[i] }); i++; }
          else { ops.push({ t: '+', s: b[j] }); j++; }
        }
        for (; i < n; i++) ops.push({ t: '-', s: a[i] });
        for (; j < m; j++) ops.push({ t: '+', s: b[j] });
      }
      for (i = finA; i < A.length; i++) ops.push({ t: '=', s: A[i] });
      return ops;
    }
    function lineaDif(op) {
      var tag = op.t === '-' ? ('d' + 'e' + 'l') : (op.t === '+' ? 'ins' : 'div');
      var clase = op.t === '-' ? 'gp-dif-quita' : (op.t === '+' ? 'gp-dif-pone' : 'gp-dif-igual');
      var n = el(tag, { class: 'gp-dif-linea ' + clase });
      n.appendChild(el('span', { class: 'gp-dif-marca', 'aria-hidden': 'true', text: op.t === '-' ? '−' : (op.t === '+' ? '+' : '') }));
      if (op.t !== '=') n.appendChild(el('span', { class: 'gp-sr', text: op.t === '-' ? T.m19 : T.m20 }));
      n.appendChild(document.createTextNode(op.s === '' ? ' ' : op.s));
      return n;
    }
    function plegado(ops) {
      var cambios = ops.length === 1 ? T.m21
        : T.m22.replace('__N__', ops.length);
      var b = el('button', {
        type: 'button', class: 'gp-dif-plegado',
        text: '··· ' + cambios + T.m23
      });
      b.addEventListener('click', function () {
        var frag = document.createDocumentFragment();
        ops.forEach(function (o) { frag.appendChild(lineaDif(o)); });
        if (b.parentNode) b.parentNode.replaceChild(frag, b);
      });
      return b;
    }
    function pintarDif(antes, despues) {
      var ops = difLineas(antes, despues);
      var caja = el('div', { class: 'gp-dif' });
      var pone = 0, quita = 0;
      ops.forEach(function (o) { if (o.t === '+') pone++; else if (o.t === '-') quita++; });
      if (!pone && !quita) {
        caja.appendChild(el('p', { class: 'gp-dif-nada', text: T.m24 }));
        return { caja: caja, pone: 0, quita: 0 };
      }
      var i = 0;
      function agregar(o) { caja.appendChild(lineaDif(o)); }
      while (i < ops.length) {
        if (ops[i].t !== '=') { agregar(ops[i]); i++; continue; }
        var j = i;
        while (j < ops.length && ops[j].t === '=') j++;
        var tramo = ops.slice(i, j);
        var arriba = i === 0 ? 0 : CONTEXTO_DIF;          // después del cambio anterior
        var abajo = j === ops.length ? 0 : CONTEXTO_DIF;  // antes del cambio siguiente
        if (tramo.length <= arriba + abajo + 1) {
          tramo.forEach(agregar);
        } else {
          tramo.slice(0, arriba).forEach(agregar);
          caja.appendChild(plegado(tramo.slice(arriba, tramo.length - abajo)));
          tramo.slice(tramo.length - abajo).forEach(agregar);
        }
        i = j;
      }
      return { caja: caja, pone: pone, quita: quita };
    }

    // ----------------------------------------------------------------- lista ---

    function resumenDe(p) {
      return { id: p.id, titulo: p.titulo, tipo: p.tipo, origen: p.origen, estado: p.estado,
               version_n: p.version_n, actualizado_en: p.actualizado_en || '', n_mensajes: p.n_mensajes || 0 };
    }
    function buscar(id) {
      for (var i = 0; i < estado.prompts.length; i++) if (mismo(estado.prompts[i].id, id)) return estado.prompts[i];
      return null;
    }
    function actualizarEnLista(p) {
      var fila = p && buscar(p.id);
      if (!fila) return;
      var cambio = false;
      ['titulo', 'tipo', 'estado', 'version_n'].forEach(function (k) {
        if (p[k] !== undefined && fila[k] !== p[k]) { fila[k] = p[k]; cambio = true; }
      });
      if (cambio) pintarLista();
    }
    function pintarLista() {
      // Si el foco estaba en un prompt de la lista, se devuelve al mismo tras repintar.
      var enfocado = document.activeElement && ui.lista.contains(document.activeElement)
        ? document.activeElement.getAttribute('data-id') : null;
      vaciar(ui.lista);
      ui.listaVacia.hidden = !(estado.listaCargada && estado.prompts.length === 0);
      var ultimoOrigen = null;
      estado.prompts.slice().sort(function (a, b) { return (a.origen || "manual").localeCompare(b.origen || "manual"); }).forEach(function (p) {
        var origen = p.origen || "manual";
        if (origen !== ultimoOrigen) {
          ui.lista.appendChild(el("li", {class: "campo-label", text: origen === "pipeline" ? T.m25 : T.m26 }));
          ultimoOrigen = origen;
        }
        var titulo = String(p.titulo || '').trim();
        var elegido = mismo(p.id, estado.sel);
        var boton = el('button', {
          type: 'button', class: 'gp-item', 'data-id': String(p.id), 'aria-current': elegido ? 'true' : null,
          title: p.actualizado_en ? T.m27.replace('__F__', p.actualizado_en) : null
        }, [
          el('span', { class: 'gp-item-titulo' + (titulo ? '' : ' gp-si' + 'n-titulo'), text: titulo || T.m28 }),
          el('span', { class: 'gp-meta' }, [
            etiquetaEstado(p.estado),
            el('span', { text: etiquetaTipo(p.tipo) }),
            el('span', { text: etiquetaVersion(p.version_n) }),
            el('span', { text: textoMensajes(p.n_mensajes) })
          ])
        ]);
        boton.addEventListener('click', function () { seleccionar(p.id, true); });
        ui.lista.appendChild(el('li', null, [boton]));
        if (enfocado !== null && enfocado === String(p.id)) boton.focus();
      });
    }
    function cargarLista(primera) {
      return api('GET', '/prompts').then(function (d) {
        estado.prompts = lista(d.prompts);
        estado.costo = typeof d.costo_mensaje === 'string' ? d.costo_mensaje : '';
        estado.listaCargada = true;
        limpiarAviso(ui.avisoLista);
        if (primera && estado.sel === null) {
          var elegido = buscar(leerSel()) || estado.prompts[0];
          if (elegido) seleccionar(elegido.id, false);
        }
        pintarLista();
        pintarControles();
      }, function (err) {
        avisoError(ui.avisoLista, err, function () { cargarLista(primera); });
      }).then(function () { ui.listaCargando.hidden = true; });
    }

    // --------------------------------------------------------------- detalle ---

    function irAlDetalle() {
      if (window.matchMedia && window.matchMedia('(max-width: 900px)').matches && ui.detalle.scrollIntoView) {
        ui.detalle.scrollIntoView({ block: 'start', behavior: 'smooth' });
      }
    }
    function guardarBorrador() { if (estado.sel !== null) borradores[String(estado.sel)] = ui.mensaje.value; }
    function pararSondeo() { if (sondeo.timer) { clearTimeout(sondeo.timer); sondeo.timer = null; } }
    function reiniciarSondeo() { pararSondeo(); sondeo.inicio = 0; sondeo.agotado = false; }

    function seleccionar(id, porClic) {
      if (mismo(id, estado.sel) && estado.detalle) { if (porClic) irAlDetalle(); return; }
      guardarBorrador();
      turno++;
      reiniciarSondeo();
      estado.sel = id;
      estado.detalle = null;
      estado.firma = '';
      estado.verOriginal = false;
      reiniciarVolver();
      cerrarEdicion();
      guardarSel(id);
      [ui.avisoDetalle, ui.avisoEntrada, ui.avisoEditar].forEach(function (z) { limpiarAviso(z); });
      ui.mensaje.value = borradores[String(id)] || '';
      ui.cuerpo.hidden = true;
      ui.detalleVacio.textContent = T.m29;
      ui.detalleVacio.hidden = false;
      pintarLista();
      cargarDetalle(id);
      if (porClic) irAlDetalle();
    }
    function reiniciarVolver() {
      if (confirmarVolver) { clearTimeout(confirmarVolver); confirmarVolver = null; }
      ui.volverOriginal.textContent = T.m30;
    }
    function soltarSeleccion(mensaje) {
      turno++;
      reiniciarSondeo();
      estado.sel = null;
      estado.detalle = null;
      estado.firma = '';
      guardarSel(null);
      ui.cuerpo.hidden = true;
      ui.detalleVacio.textContent = T.m31;
      ui.detalleVacio.hidden = false;
      if (mensaje) aviso(ui.avisoDetalle, 'warn', mensaje);
      pintarLista();
    }
    function cargarDetalle(id, silencioso) {
      var t = turno;
      if (!silencioso) ui.detalle.setAttribute('aria-busy', 'true');
      return api('GET', rutaPrompt(id)).then(function (d) {
        if (t !== turno) return;
        aplicarDetalle(d);
      }, function (err) {
        if (t !== turno) return;
        if (err.status === 404) {
          estado.prompts = estado.prompts.filter(function (p) { return !mismo(p.id, id); });
          soltarSeleccion(T.m32);
          return;
        }
        if (!estado.detalle) ui.detalleVacio.textContent = T.m33;
        avisoError(ui.avisoDetalle, err, function () { cargarDetalle(id); });
      }).then(function () { if (t === turno) ui.detalle.removeAttribute('aria-busy'); });
    }
    function recargarDetalle() {
      if (estado.sel === null) return;
      estado.firma = '';
      sondeo.inicio = 0;
      sondeo.agotado = false;
      cargarDetalle(estado.sel);
    }
    function aplicarDetalle(d) {
      if (!d || typeof d !== 'object' || !d.prompt || typeof d.prompt !== 'object') return;
      d.mensajes = lista(d.mensajes);
      d.pendiente = !!d.pendiente;
      var antes = estado.detalle;
      var respondio = !!antes && antes.pendiente && !d.pendiente;
      estado.detalle = d;
      actualizarEnLista(d.prompt);
      if (d.pendiente) {
        if (!sondeo.timer && !sondeo.agotado && modoActivo) {
          if (!sondeo.inicio) sondeo.inicio = Date.now();
          sondeo.timer = setTimeout(sondear, SONDEO_MS);
        }
      } else {
        reiniciarSondeo();
      }
      pintarDetalle();
      if (respondio) cargarLista();  // n_mensajes al día
    }
    function sondear() {
      sondeo.timer = null;
      var id = estado.sel, t = turno;
      if (id === null || !modoActivo) return;
      if (Date.now() - sondeo.inicio > SONDEO_MAX_MS) {
        sondeo.agotado = true;
        pintarDetalle();
        return;
      }
      api('GET', rutaPrompt(id)).then(function (d) {
        if (t !== turno) return;
        aplicarDetalle(d);
      }, function () {
        // Un tropiezo de red no corta la espera: se reintenta un poco más tarde.
        if (t !== turno || !modoActivo || sondeo.timer) return;
        sondeo.timer = setTimeout(sondear, SONDEO_MS * 2);
      });
    }

    function nodoPensando() {
      return el('div', { class: 'gp-pensando' }, [
        el('span', { class: 'gp-puntos', 'aria-hidden': 'true' }, [el('i'), el('i'), el('i')]),
        el('span', { text: T.m34 })
      ]);
    }
    function msjPensando() {
      var li = el('li', { class: 'gp-msj gp-msj-claude gp-msj-pendiente' }, [
        el('span', { class: 'gp-msj-autor', text: 'Claude' }),
        nodoPensando()
      ]);
      if (sondeo.agotado) {
        li.appendChild(el('p', { class: 'gp-ayuda', text: T.m35 }));
        li.appendChild(el('button', { type: 'button', class: 'btn-guarda' + 'r btn-xs', text: T.m36, onclick: recargarDetalle }));
      }
      return li;
    }
    function msjPersona(m) {
      return el('li', { class: 'gp-msj gp-msj-persona', title: m.creado_en || null }, [
        el('span', { class: 'gp-msj-autor', text: T.m37 }),
        el('p', { class: 'gp-msj-texto', text: normalizar(m.contenido) })
      ]);
    }
    function listaProblemas(titulo, probs, clase) {
      return el('div', { class: clase }, [
        el('strong', { text: titulo }),
        el('ul', null, probs.map(function (x) { return el('li', { text: String(x) }); }))
      ]);
    }
    function tarjetaPropuesta(m, p) {
      var probs = lista(m.problemas);
      var aprobado = esAprobado(p);
      var enUso = !!m.aplicada;
      var dif = pintarDif(p.texto_vigente, m.propuesta);
      var cab = el('div', { class: 'gp-propuesta-cab' }, [el('strong', { text: T.m38 })]);
      if (dif.pone || dif.quita) {
        cab.appendChild(el('span', { class: 'gp-dif-resumen' }, [
          el('span', { class: 'gp-mas', text: '+' + dif.pone }),
          el('span', { class: 'gp-menos', text: '−' + dif.quita }),
          el('span', { text: (dif.pone + dif.quita) === 1 ? T.m39 : T.m40 })
        ]));
      }
      var card = el('div', { class: 'gp-propuesta' + (enUso ? ' gp-propuesta-e' + 'n-uso' : '') }, [cab, dif.caja]);
      if (probs.length) card.appendChild(listaProblemas(T.m41, probs, 'gp-problemas-propuesta'));
      var zona = el('div', { class: 'gp-aviso', hidden: true, 'aria-live': 'polite' });
      var pie = el('div', { class: 'gp-propuesta-pie' });
      if (enUso) {
        pie.appendChild(el('span', { class: 'tag-estado tag-e' + 'n-uso', text: T.m42 }));
      } else {
        var bloqueado = probs.length > 0 || aprobado;
        var b = el('button', { type: 'button', class: 'btn-generar btn-sm gp-usar', text: T.m43 });
        b.dataset.bloqueado = bloqueado ? '1' : '';
        b.disabled = bloqueado || estado.ocupado;
        b.addEventListener('click', function () { usarVersion(m.id, zona); });
        pie.appendChild(b);
        if (probs.length) pie.appendChild(el('small', { text: T.m44 }));
        else if (aprobado) pie.appendChild(el('small', { text: T.m45 }));
      }
      card.appendChild(pie);
      card.appendChild(zona);
      return card;
    }
    function msjClaude(m, p) {
      var li = el('li', { class: 'gp-msj gp-msj-claude', title: m.creado_en || null }, [
        el('span', { class: 'gp-msj-autor', text: 'Claude' })
      ]);
      if (m.estado === 'error') {
        li.classList.add('gp-msj-error');
        li.appendChild(el('p', { class: 'gp-msj-texto', text: T.m46 }));
        if (m.contenido) li.appendChild(el('p', { class: 'gp-msj-texto gp-msj-detalle', text: normalizar(m.contenido) }));
        li.appendChild(el('p', { class: 'gp-ayuda', text: T.m47 }));
        return li;
      }
      if (m.contenido) li.appendChild(el('p', { class: 'gp-msj-texto', text: normalizar(m.contenido) }));
      if (typeof m.propuesta === 'string' && m.propuesta !== '') li.appendChild(tarjetaPropuesta(m, p));
      return li;
    }
    function pintarHilo() {
      vaciar(ui.hilo);
      var d = estado.detalle;
      if (!d) return;
      var p = d.prompt;
      var hayPendiente = false;
      d.mensajes.forEach(function (m) {
        if (!m || typeof m !== 'object') return;
        if (m.rol === 'persona') { ui.hilo.appendChild(msjPersona(m)); return; }
        if (m.estado === 'pendiente') { hayPendiente = true; ui.hilo.appendChild(msjPensando()); return; }
        ui.hilo.appendChild(msjClaude(m, p));
      });
      if (d.pendiente && !hayPendiente) ui.hilo.appendChild(msjPensando());
      ui.hiloVacio.hidden = d.mensajes.length > 0 || d.pendiente;
    }

    function pintarDetalle(forzar) {
      var d = estado.detalle;
      if (!d) { ui.cuerpo.hidden = true; ui.detalleVacio.hidden = false; return; }
      var firma = JSON.stringify(d) + '|' + sondeo.agotado;
      if (!forzar && firma === estado.firma) { pintarControles(); return; }
      estado.firma = firma;
      var p = d.prompt;
      ui.detalleVacio.hidden = true;
      ui.cuerpo.hidden = false;

      var titulo = String(p.titulo || '').trim();
      ui.titulo.textContent = titulo || T.m28;
      ui.titulo.classList.toggle('gp-si' + 'n-titulo', !titulo);
      vaciar(ui.meta);
      ui.meta.appendChild(etiquetaEstado(p.estado));
      ui.meta.appendChild(el('span', { class: 'gp-version', text: etiquetaVersion(p.version_n) }));
      ui.meta.appendChild(el('span', { text: etiquetaTipo(p.tipo) }));

      var vigente = normalizar(p.texto_vigente), original = normalizar(p.texto_original);
      ui.texto.textContent = vigente;
      ui.original.textContent = original;
      var igual = vigente === original;
      ui.originalIgual.hidden = !igual;
      ui.original.hidden = igual;
      ui.volverOriginal.hidden = igual;
      pintarOriginal();

      var probs = lista(p.problemas);
      vaciar(ui.problemasLista);
      probs.forEach(function (x) { ui.problemasLista.appendChild(el('li', { text: String(x) })); });
      ui.problemas.hidden = probs.length === 0;

      var ctx = normalizar(p.contexto).trim();
      var fijos = lista(p.texto_fijo).map(function (x) { return String(x); }).filter(function (x) { return x.trim() !== ''; });
      ui.contextoTexto.textContent = ctx;
      ui.contextoTextoCaja.hidden = !ctx;
      vaciar(ui.fijos);
      fijos.forEach(function (x) { ui.fijos.appendChild(el('li', { text: x })); });
      ui.fijosCaja.hidden = fijos.length === 0;
      ui.contexto.hidden = !ctx && fijos.length === 0;

      if (esAprobado(p) && estado.editando) cerrarEdicion();
      pintarHilo();
      pintarControles();
    }

    function pintarOriginal() {
      ui.originalCaja.hidden = !estado.verOriginal;
      ui.verOriginal.textContent = estado.verOriginal ? T.m48 : T.m49;
      ui.verOriginal.setAttribute('aria-expanded', estado.verOriginal ? 'true' : 'false');
    }

    function pintarControles() {
      var d = estado.detalle, p = d ? d.prompt : null;
      var aprobado = esAprobado(p), pendiente = !!(d && d.pendiente);
      var probs = p ? lista(p.problemas) : [];
      var ocupado = estado.ocupado;

      ui.aprobar.hidden = aprobado;
      ui.reabrir.hidden = !aprobado;
      ui.aprobar.disabled = !d || ocupado || pendiente || probs.length > 0 || estado.editando;
      ui.reabrir.disabled = !d || ocupado;
      var nota = '';
      if (d && !aprobado) {
        if (probs.length) nota = T.m50;
        else if (pendiente) nota = T.m51;
        else if (estado.editando) nota = T.m52;
      } else if (aprobado) {
        nota = T.m53;
      }
      ui.notaAprobar.textContent = nota;
      ui.notaAprobar.hidden = !nota;

      ui.editarBtn.hidden = estado.editando;
      ui.editarBtn.disabled = !d || ocupado || aprobado;
      ui.editarGuardar.disabled = ocupado;
      ui.volverOriginal.disabled = !d || ocupado || aprobado;
      ui.copiar.disabled = !d;

      ui.mensaje.disabled = !d || aprobado;
      ui.enviar.disabled = !d || aprobado || pendiente || estado.enviando || ocupado;
      ui.enviar.textContent = estado.enviando ? T.m54 : (T.m55 + (estado.costo ? ' · ' + estado.costo : ''));
      var notaEntrada = '';
      if (aprobado) notaEntrada = T.m56;
      else if (pendiente) notaEntrada = T.m57;
      ui.notaEntrada.textContent = notaEntrada;
      ui.notaEntrada.hidden = !notaEntrada;

      Array.prototype.forEach.call(ui.hilo.querySelectorAll('.gp-usar'), function (b) {
        b.disabled = ocupado || b.dataset.bloqueado === '1';
      });
    }

    function resaltarTexto() {
      ui.texto.classList.remove('gp-recien');
      void ui.texto.offsetWidth;
      ui.texto.classList.add('gp-recien');
    }

    // ------------------------------------------------------------- acciones ---

    function accion(ruta, cuerpo, zona, alExito) {
      if (estado.sel === null || !estado.detalle || estado.ocupado) return;
      var id = estado.sel, t = turno;
      estado.ocupado = true;
      limpiarAviso(ui.avisoDetalle);
      limpiarAviso(zona);
      pintarControles();
      api('POST', rutaPrompt(id, ruta), cuerpo).then(function (r) {
        if (t !== turno) return;
        estado.ocupado = false;
        if (alExito) alExito(r);
        if (r.prompt && typeof r.prompt === 'object' && Array.isArray(r.mensajes)) {
          // Las rutas devuelven el detalle completo (prompt + mensajes + pendiente).
          aplicarDetalle(r);
        } else {
          if (r.prompt && typeof r.prompt === 'object') {
            estado.detalle.prompt = Object.assign({}, estado.detalle.prompt, r.prompt);
          }
          pintarDetalle(true);
          actualizarEnLista(estado.detalle.prompt);
          cargarDetalle(id, true);  // trae las marcas «aplicada» de los mensajes
        }
        cargarLista();  // orden por último cambio y n_mensajes al día
      }, function (err) {
        if (t !== turno) return;
        avisoError(zona || ui.avisoDetalle, err);
      }).then(function () {
        estado.ocupado = false;
        pintarControles();
      });
    }
    function versionActual() { return estado.detalle ? estado.detalle.prompt.version_n : null; }
    function usarVersion(mensajeId, zona) {
      accion('/usar', { mensaje_id: mensajeId, version_n: versionActual() }, zona, function () {
        resaltarTexto();
        aviso(ui.avisoDetalle, 'ok', mensajeId === null
          ? T.m58
          : T.m59);
      });
    }

    function abrirEdicion() {
      var d = estado.detalle;
      if (!d || esAprobado(d.prompt)) return;
      estado.editando = true;
      ui.editarTexto.value = normalizar(d.prompt.texto_vigente);
      ui.editar.hidden = false;
      ui.texto.hidden = true;
      limpiarAviso(ui.avisoEditar);
      pintarControles();
      ui.editarTexto.focus();
    }
    function cerrarEdicion() {
      estado.editando = false;
      ui.editar.hidden = true;
      ui.texto.hidden = false;
      limpiarAviso(ui.avisoEditar);
    }
    function guardarEdicion() {
      var d = estado.detalle;
      if (!d) return;
      var texto = ui.editarTexto.value;
      if (!texto.trim()) { aviso(ui.avisoEditar, 'error', T.m60); return; }
      if (normalizar(texto) === normalizar(d.prompt.texto_vigente)) { cerrarEdicion(); pintarControles(); return; }
      accion('/editar', { texto: texto, version_n: versionActual() }, ui.avisoEditar, function () {
        cerrarEdicion();
        resaltarTexto();
        aviso(ui.avisoDetalle, 'ok', T.m61);
      });
    }

    function enviarMensaje() {
      var d = estado.detalle;
      if (!d || estado.enviando || estado.ocupado || d.pendiente || esAprobado(d.prompt)) return;
      var texto = ui.mensaje.value.trim();
      if (!texto) {
        aviso(ui.avisoEntrada, 'error', T.m62);
        ui.mensaje.focus();
        return;
      }
      var id = estado.sel, t = turno;
      estado.enviando = true;
      limpiarAviso(ui.avisoEntrada);
      pintarControles();
      api('POST', rutaPrompt(id, '/mensajes'), { mensaje: texto }).then(function (r) {
        if (t !== turno) { borradores[String(id)] = ''; return; }
        ui.mensaje.value = '';
        borradores[String(id)] = '';
        // Se pinta ya lo enviado y la espera; el sondeo trae la verdad del servidor.
        estado.detalle.mensajes = estado.detalle.mensajes.concat([
          { id: null, rol: 'persona', contenido: texto, propuesta: null, problemas: [], estado: 'ok', aplicada: false, creado_en: '' },
          { id: r.mensaje_id, rol: 'claude', contenido: '', propuesta: null, problemas: [], estado: 'pendiente', aplicada: false, creado_en: '' }
        ]);
        estado.detalle.pendiente = true;
        reiniciarSondeo();
        estado.enviando = false;
        aplicarDetalle(estado.detalle);
        var ultimo = ui.hilo.lastElementChild;
        if (ultimo && ultimo.scrollIntoView) ultimo.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
      }, function (err) {
        if (t !== turno) return;
        avisoError(ui.avisoEntrada, err);
      }).then(function () {
        estado.enviando = false;
        pintarControles();
      });
    }

    function copiar(texto) {
      function listo(ok) {
        ui.copiar.textContent = ok ? T.m63 : T.m64;
        setTimeout(function () { ui.copiar.textContent = T.m65; }, 1600);
      }
      function aLaAntigua() {
        var t = document.createElement('textarea');
        t.value = texto;
        t.setAttribute('readonly', '');
        t.style.position = 'fixed';
        t.style.top = '0';
        t.style.opacity = '0';
        document.body.appendChild(t);
        t.select();
        var ok = false;
        try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
        document.body.removeChild(t);
        return ok;
      }
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(texto).then(function () { listo(true); }, function () { listo(aLaAntigua()); });
      } else {
        listo(aLaAntigua());
      }
    }

    // --------------------------------------------------------------- eventos ---

    function mostrarNuevo(abrir) {
      ui.nuevo.hidden = !abrir;
      ui.nuevoBtn.setAttribute('aria-expanded', abrir ? 'true' : 'false');
      if (abrir) ui.nuevoTitulo.focus();
    }
    ui.nuevoBtn.addEventListener('click', function () { mostrarNuevo(ui.nuevo.hidden); });
    ui.nuevoCancelar.addEventListener('click', function () {
      mostrarNuevo(false);
      limpiarAviso(ui.avisoNuevo);
      ui.nuevoTexto.classList.remove('co' + 'n-error');
    });
    ui.nuevo.addEventListener('submit', function (e) {
      e.preventDefault();
      if (estado.creando) return;
      var texto = ui.nuevoTexto.value;
      ui.nuevoTexto.classList.remove('co' + 'n-error');
      if (!texto.trim()) {
        ui.nuevoTexto.classList.add('co' + 'n-error');
        aviso(ui.avisoNuevo, 'error', T.m66);
        ui.nuevoTexto.focus();
        return;
      }
      estado.creando = true;
      ui.nuevoGuardar.disabled = true;
      ui.nuevoGuardar.textContent = T.m67;
      limpiarAviso(ui.avisoNuevo);
      api('POST', '/prompts', {
        titulo: ui.nuevoTitulo.value.trim(),
        texto: texto,
        contexto: ui.nuevoContexto.value,
        texto_fijo: ui.nuevoFijo.value,
        tipo: ui.nuevoTipo.value
      }).then(function (r) {
        var p = r.prompt;
        ui.nuevo.reset();
        mostrarNuevo(false);
        if (p && typeof p === 'object' && p.id !== undefined && p.id !== null) {
          estado.listaCargada = true;
          estado.prompts = [resumenDe(p)].concat(estado.prompts.filter(function (x) { return !mismo(x.id, p.id); }));
          seleccionar(p.id, true);
          aplicarDetalle({ prompt: p, mensajes: lista(r.mensajes), pendiente: !!r.pendiente });
        }
        cargarLista();
      }, function (err) {
        avisoError(ui.avisoNuevo, err);
      }).then(function () {
        estado.creando = false;
        ui.nuevoGuardar.disabled = false;
        ui.nuevoGuardar.textContent = T.m68;
      });
    });

    ui.copiar.addEventListener('click', function () {
      if (estado.detalle) copiar(normalizar(estado.detalle.prompt.texto_vigente));
    });
    ui.verOriginal.addEventListener('click', function () {
      estado.verOriginal = !estado.verOriginal;
      pintarOriginal();
    });
    ui.volverOriginal.addEventListener('click', function () {
      // Dos toques: volver al original descarta el vigente (una edición a mano
      // no queda en el chat). Las propuestas de Claude sí siguen disponibles.
      if (!confirmarVolver) {
        ui.volverOriginal.textContent = T.m69;
        confirmarVolver = setTimeout(function () {
          confirmarVolver = null;
          ui.volverOriginal.textContent = T.m30;
        }, 4000);
        return;
      }
      reiniciarVolver();
      usarVersion(null, ui.avisoDetalle);
    });
    ui.editarBtn.addEventListener('click', abrirEdicion);
    ui.editarCancelar.addEventListener('click', function () { cerrarEdicion(); pintarControles(); });
    ui.editarGuardar.addEventListener('click', guardarEdicion);
    ui.editarTexto.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); guardarEdicion(); }
    });
    ui.aprobar.addEventListener('click', function () {
      accion('/aprobar', { version_n: versionActual() }, ui.avisoDetalle, function () {
        aviso(ui.avisoDetalle, 'ok', T.m70);
      });
    });
    ui.reabrir.addEventListener('click', function () {
      accion('/reabrir', {}, ui.avisoDetalle, function () {
        aviso(ui.avisoDetalle, 'ok', T.m71);
      });
    });
    ui.entrada.addEventListener('submit', function (e) { e.preventDefault(); enviarMensaje(); });
    ui.mensaje.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); enviarMensaje(); }
    });

    // Se carga solo cuando el modo se abre; al salir del modo se corta el sondeo.
    document.addEventListener('crear:modo', function (e) {
      var activo = !!(e.detail && e.detail.modo === 'flowplus');
      if (activo === modoActivo) return;
      modoActivo = activo;
      if (!activo) { pararSondeo(); return; }
      if (!estado.listaCargada) { cargarLista(true); return; }
      if (estado.sel !== null) { sondeo.inicio = 0; sondeo.agotado = false; cargarDetalle(estado.sel, true); }
    });

    // El panel de guiones pide abrir un prompt del pipeline en este chat.
    document.addEventListener('gp:abrir-prompt', function (e) {
      var id = e.detail && e.detail.id;
      if (id === undefined || id === null) return;
      cargarLista(false).then(function () { seleccionar(id, true); });
    });

    pintarControles();
  })();
