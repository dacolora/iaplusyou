// Autoguardado del editor (spec §5): espera `esperaMs` desde el último
// cambio, manda un solo PUT a la vez con {documento, version_n} y guarda la
// versión que devuelve el servidor (CAS). Un cambio que llega mientras se
// guarda sale en el siguiente PUT. 409 = otra pestaña guardó antes: queda en
// «conflicto» y no vuelve a guardar hasta recargar. Sin red o con 400 queda
// en «error» y reintenta con el próximo cambio. El servidor manda en `error`
// una frase para la persona y, si hay, en `detalle` lo técnico (la ruta del
// validador): queda en `this.detalle` y le llega a `alCambiar` como tercer
// argumento (la página lo pone en el `title`, capa 4c).
export const MENSAJE_SESION = "Tu sesión terminó: recarga la página e inicia sesión.";

// Capa 4c: ¿la respuesta es la página de entrar? Con la sesión vencida el
// servidor redirige a /login y `fetch` sigue la redirección: llega marcada
// `redirected` con la URL de /login (un PUT, además, como 405), o como una
// página HTML con 200. Nada más: un 5xx con HTML (un 500 de Flask, un 502/504
// de nginx durante un despliegue) NO es la sesión — decir «recarga» ahí haría
// perder el cambio pendiente. Sin cabeceras (las pruebas) no se asume nada.
export function sesionTerminada(r) {
  if (r?.redirected && /\/login(?:[/?#]|$)/.test(String(r.url ?? ""))) return true;
  const tipo = r?.headers?.get?.("content-type") ?? "";
  return r?.status === 200 && /text\/html/i.test(tipo);
}

function enviarPorDefecto(url, cuerpo) {
  return fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(cuerpo),
  });
}

export class Guardado {
  constructor({ url, versionN, enviar = enviarPorDefecto, programar = (fn, ms) => setTimeout(fn, ms),
    cancelar = (id) => clearTimeout(id), esperaMs = 1200, alCambiar = () => {} }) {
    Object.assign(this, { url, versionN, enviar, programar, cancelar, esperaMs, alCambiar });
    this.estado = "guardado";
    this.mensaje = "";
    this.detalle = "";
    this.pendiente = null;
    this.enVuelo = null;
    this.timer = null;
  }

  _poner(estado, mensaje = "", detalle = "") {
    this.estado = estado;
    this.mensaje = mensaje;
    this.detalle = detalle;
    this.alCambiar(estado, mensaje, detalle);
  }

  get sinGuardar() {
    return Boolean(this.pendiente) || this.estado === "guardando";
  }

  pedir(doc) {
    if (this.estado === "conflicto") return;
    this.pendiente = doc;
    if (!this.enVuelo) this._poner("pendiente");
    if (this.timer !== null) this.cancelar(this.timer);
    this.timer = this.programar(() => { this.timer = null; return this.ahora(); }, this.esperaMs);
  }

  async ahora() {
    if (this.enVuelo) {
      await this.enVuelo;
      return this.ahora();
    }
    if (!this.pendiente || this.estado === "conflicto") return;
    const doc = this.pendiente;
    this.pendiente = null;
    this._poner("guardando");
    this.enVuelo = (async () => {
      try {
        const r = await this.enviar(this.url, { documento: doc, version_n: this.versionN });
        if (sesionTerminada(r)) {
          // nada se guardó: el cambio sigue pendiente (y el aviso al salir lo protege)
          this.pendiente = this.pendiente ?? doc;
          this._poner("error", MENSAJE_SESION);
          return;
        }
        const cuerpo = await r.json().catch(() => ({}));
        if (r.status === 200) {
          this.versionN = cuerpo.version_n;
          this._poner(this.pendiente ? "pendiente" : "guardado");
        } else if (r.status === 409) {
          this._poner("conflicto", cuerpo.error || "La edición cambió en otra pestaña; recarga para seguir.");
        } else {
          this.pendiente = this.pendiente ?? doc;
          const porDefecto = r.status >= 500
            ? `el servidor falló (error ${r.status}): se guarda con el próximo cambio.`
            : `No se pudo guardar (error ${r.status}).`;
          this._poner("error", cuerpo.error || porDefecto, cuerpo.detalle || "");
        }
      } catch {
        this.pendiente = this.pendiente ?? doc;
        this._poner("error", "Sin conexión: se guarda con el próximo cambio.");
      } finally {
        this.enVuelo = null;
      }
    })();
    await this.enVuelo;
    if (this.pendiente && this.estado === "pendiente") return this.ahora();
  }
}
