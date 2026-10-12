// Planes (planes 6/8, spec 2026-10-09 §5.2 y §8). Script clásico sin textos
// propios (los trae el servidor ya traducidos, en el HTML o en data-*):
// 1. Configuración › Plan: pide el fragmento (data-plan-panel) la primera vez
//    que el apartado se ve y al volver a abrirlo; si el fragmento trae un pago
//    pendiente (data-plan-sondeo), sondea su estado cada 3 s hasta 90 s y
//    vuelve a pedir el panel cuando Wompi responde.
// 2. El formulario de alta / cambio de tarjeta (#plan-alta): el botón del
//    widget de Wompi queda bloqueado hasta marcar las tres casillas (el
//    servidor las exige igual), las pestañas Tarjeta / Nequi y el camino de
//    Nequi: pedir el token, sondear hasta APPROVED y enviar el formulario.
// Los fetch pasan por el envoltorio de static/cobros.js (lo carga base.html).
(function (raiz) {
  'use strict';
  var doc = raiz.document;
  var CABECERAS = { 'X-Requested-With': 'fetch' };
  var CADA_MS = 3000;
  var LIMITE_PAGO_MS = 90000;
  var LIMITE_NEQUI_MS = 180000;
  var REABRIR_MS = 3000;

  // ¿Están marcadas todas las casillas? (lista de elementos con .checked)
  function casillasListas(casillas) {
    if (!casillas || !casillas.length) return false;
    for (var i = 0; i < casillas.length; i++) if (!casillas[i].checked) return false;
    return true;
  }

  // Qué hacer con el estado de un pago de plan: 'final' (ya no está pendiente),
  // 'tarde' (pasó el límite) o 'seguir'.
  function pasoPago(datos, transcurridoMs) {
    if (datos && datos.estado && datos.estado !== 'pendiente') return 'final';
    return transcurridoMs >= LIMITE_PAGO_MS ? 'tarde' : 'seguir';
  }

  // Qué hacer con el estado de un token de Nequi.
  function pasoNequi(datos, transcurridoMs) {
    var estado = datos && datos.estado;
    if (estado === 'APPROVED') return 'aprobado';
    if (estado === 'DECLINED') return 'rechazado';
    return transcurridoMs >= LIMITE_NEQUI_MS ? 'tarde' : 'seguir';
  }

  function pedir(url, opciones) {
    var o = opciones || {};
    o.headers = o.headers || CABECERAS;
    o.credentials = 'same-origin';
    o.cache = 'no-store';
    return raiz.fetch(url, o).then(function (r) {
      if (r.redirected) throw new Error('sesion');
      return r;
    });
  }

  // ------------------------------------------------- Configuración › Plan ---

  function iniciarPanel() {
    var caja = doc.querySelector('[data-plan-panel]');
    if (!caja) return;
    var estado = 'nada';   // nada | pidiendo | listo
    var cargadoEn = 0;
    var seVeia = false;
    var sondeoVivo = 0;
    function visible() { return caja.getClientRects().length > 0; }
    function marcarError() {
      var cargando = caja.querySelector('[data-plan-cargando]');
      var error = caja.querySelector('[data-plan-error]');
      if (cargando) cargando.hidden = true;
      if (error) error.hidden = false;
    }
    function cargar(forzar) {
      var ve = visible();
      var reabrir = ve && !seVeia;
      seVeia = ve;
      if (!ve || estado === 'pidiendo') return;
      if (!forzar && estado === 'listo' && !(reabrir && Date.now() - cargadoEn >= REABRIR_MS)) return;
      var anterior = estado;
      estado = 'pidiendo';
      pedir(caja.getAttribute('data-plan-panel'))
        .then(function (r) { if (!r.ok) throw new Error('plan ' + r.status); return r.text(); })
        .then(function (html) {
          caja.innerHTML = html;
          estado = 'listo';
          cargadoEn = Date.now();
          sondear();
        })
        .catch(function () {
          estado = anterior === 'listo' ? 'listo' : 'nada';
          if (estado === 'nada') marcarError();
        });
    }
    function sondear() {
      var marca = caja.querySelector('[data-plan-sondeo]');
      if (!marca) return;
      var url = marca.getAttribute('data-plan-sondeo');
      var inicio = Date.now();
      var mio = ++sondeoVivo;
      function vuelta() {
        if (mio !== sondeoVivo) return;
        pedir(url).then(function (r) { return r.ok ? r.json() : null; })
          .then(seguir, function () { seguir(null); });
      }
      function seguir(d) {
        if (mio !== sondeoVivo) return;
        var paso = pasoPago(d, Date.now() - inicio);
        if (paso === 'final') { cargar(true); return; }
        if (paso === 'seguir') setTimeout(vuelta, CADA_MS);
      }
      setTimeout(vuelta, CADA_MS);
    }
    function luego() { setTimeout(function () { cargar(false); }, 0); }
    cargar(false);
    raiz.addEventListener('cr:tab', luego);
    raiz.addEventListener('hashchange', luego);
    doc.addEventListener('click', function (ev) {
      if (ev.target.closest && ev.target.closest('.config-apartados [data-apartado], .sidebar-item')) luego();
    });
  }

  // ------------------------------------------- alta y cambio de tarjeta ---

  function iniciarAlta() {
    var caja = doc.getElementById('plan-alta');
    var form = caja && caja.querySelector('[data-plan-form]');
    if (!form) return;
    var casillas = form.querySelectorAll('[data-plan-casilla]');
    var aviso = form.querySelector('[data-plan-widget-aviso]');
    var tipo = form.querySelector('[data-plan-tipo]');
    var token = form.querySelector('[data-plan-token]');
    var texto = function (nombre) { return caja.getAttribute('data-texto-' + nombre) || ''; };

    var medioActual = 'CARD';
    // El botón que pinta el widget de Wompi: su script es hijo directo del formulario (lo exige el widget) y el
    // botón queda a su lado, también hijo directo. Nuestros botones viven dentro de otros elementos.
    function botonesDelWidget() {
      return Array.prototype.filter.call(form.children, function (el) {
        return el.tagName === 'BUTTON' || (el.classList && el.classList.contains('waybox-button'));
      });
    }
    function revisarCasillas() {
      var listas = casillasListas(casillas);
      var bloqueado = !listas || medioActual !== 'CARD';
      botonesDelWidget().forEach(function (b) {
        b.classList.toggle('plan-bloqueado', !listas);
        b.hidden = medioActual !== 'CARD';
        b.setAttribute('aria-disabled', bloqueado ? 'true' : 'false');
        b.inert = bloqueado;
      });
      if (aviso) aviso.hidden = listas;
      return listas;
    }
    Array.prototype.forEach.call(casillas, function (c) { c.addEventListener('change', revisarCasillas); });
    revisarCasillas();
    // Enter en el correo o el celular no envía el formulario: el botón por defecto es el del widget (type=submit)
    // y abriría Wompi sin las casillas, o mandaría el formulario sin token.
    form.addEventListener('keydown', function (ev) {
      if (ev.key === 'Enter' && ev.target && ev.target.tagName === 'INPUT') ev.preventDefault();
    });
    // El widget pinta su botón cuando termina de cargar: se bloquea apenas aparece.
    if (raiz.MutationObserver) new raiz.MutationObserver(revisarCasillas).observe(form, { childList: true });

    // Pestañas Tarjeta / Nequi (sin JS solo se ve la tarjeta).
    var botones = form.querySelector('[data-plan-medios]');
    if (botones) {
      botones.hidden = false;
      botones.addEventListener('click', function (ev) {
        var b = ev.target.closest('[data-plan-medio]');
        if (!b) return;
        var medio = b.getAttribute('data-plan-medio');
        Array.prototype.forEach.call(botones.querySelectorAll('[data-plan-medio]'), function (x) {
          var activo = x === b;
          x.classList.toggle('activo', activo);
          x.setAttribute('aria-selected', activo ? 'true' : 'false');
        });
        Array.prototype.forEach.call(form.querySelectorAll('[data-plan-panel-medio]'), function (p) {
          p.hidden = p.getAttribute('data-plan-panel-medio') !== medio;
        });
        if (tipo) tipo.value = medio;
        if (token) token.value = '';
        medioActual = medio;
        revisarCasillas();
      });
    }

    // Nequi: pedir el token, sondear hasta que la persona apruebe en su app y enviar.
    var boton = form.querySelector('[data-plan-nequi]');
    var celular = form.querySelector('[data-plan-celular]');
    var estadoNequi = form.querySelector('[data-plan-nequi-estado]');
    function decir(t) { if (estadoNequi) estadoNequi.textContent = t; }
    if (boton) boton.addEventListener('click', function () {
      if (!revisarCasillas()) { decir(aviso ? aviso.textContent : ''); return; }
      boton.disabled = true;
      var cuerpo = new raiz.URLSearchParams();
      cuerpo.set('celular', celular ? celular.value : '');
      pedir(boton.getAttribute('data-plan-nequi'), {
        method: 'POST', body: cuerpo,
        headers: { 'X-Requested-With': 'fetch', 'Content-Type': 'application/x-www-form-urlencoded' }
      }).then(function (r) { return r.json().catch(function () { return null; }); })
        .then(function (d) {
          if (!d || !d.ok || !d.token || !d.estado_url) {
            boton.disabled = false;
            decir((d && d.error) || texto('error'));
            return;
          }
          decir(texto('esperando'));
          esperarNequi(d.token, d.estado_url);
        }, function () { boton.disabled = false; decir(texto('error')); });
    });
    function esperarNequi(valor, url) {
      var inicio = Date.now();
      function vuelta() {
        pedir(url).then(function (r) { return r.ok ? r.json() : null; }).then(seguir, function () { seguir(null); });
      }
      function seguir(d) {
        var paso = pasoNequi(d, Date.now() - inicio);
        if (paso === 'aprobado') {
          decir(texto('aprobado'));
          if (tipo) tipo.value = 'NEQUI';
          if (token) token.value = valor;
          if (form.requestSubmit) form.requestSubmit(); else form.submit();
          return;
        }
        if (paso === 'seguir') { setTimeout(vuelta, CADA_MS); return; }
        if (boton) boton.disabled = false;
        decir(texto(paso === 'rechazado' ? 'rechazado' : 'tarde'));
      }
      setTimeout(vuelta, CADA_MS);
    }
  }

  raiz.CobrosPlanes = { casillasListas: casillasListas, pasoPago: pasoPago, pasoNequi: pasoNequi,
                        LIMITE_PAGO_MS: LIMITE_PAGO_MS, LIMITE_NEQUI_MS: LIMITE_NEQUI_MS };
  if (doc && doc.querySelector) {
    iniciarPanel();
    iniciarAlta();
  }
})(typeof window !== 'undefined' ? window : this);
