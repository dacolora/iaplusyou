"""PND-299 (decisión 2026-10-13, lote 1; Daniel: «podríamos darle hasta 2 o 3 dólares gratis para la generación; de
resto todo de cuenta del cliente»). Las cuatro ayudas con IA que pagaba Creatv (`_creatv`) y nunca frenaban, ni con
saldo 0 ni sin correo verificado —el director «Armar prompt» (crear y rearmar), «Describir referencias», «Sugerir
sonido» y «Analizar marca»— cobran del saldo del proyecto como todo lo demás: precio a la vista, freno, reserva y el
gasto anotado al proyecto. Y cada proyecto nuevo recibe un saldo de bienvenida (US$ 2, editable en /admin/cobros), una
sola vez, cuando una cuenta suya queda con el correo verificado."""
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from tests.test_rutas_crear_director import _crear
from tests.test_rutas_crear_director import app as app_crear  # noqa: F401 — fixture

MISMO = {"Sec-Fetch-Site": "same-origin"}
USO = SimpleNamespace(input_tokens=1000, output_tokens=100)     # costo_real: (1000 × 2 + 100 × 10) / 1e6 = 0,003


@pytest.fixture()
def libro(margen_1_5):
    from cobros import libro as mod
    return mod


def _cobra(libro, cliente="acme", milesimas=0, pospago=None):
    import db
    libro.configurar(cliente, usuario="admin", cobrar=True, pospago=pospago)
    if milesimas:
        with db.conectar() as con:
            libro.acreditar(con, cliente, "ajuste", milesimas, "ajuste", usuario="admin", detalle="prueba")


def _gastos(cliente="acme"):
    import db
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(db.gasto).where(db.gasto.c.cliente == cliente)).all()]


def _movimientos(cliente="acme"):
    import db
    m = db.movimiento_saldo
    with db.conectar() as con:
        return [dict(r._mapping) for r in con.execute(sa.select(m).where(m.c.cliente == cliente)
                                                      .order_by(m.c.id)).all()]


def _reservas(cliente="acme"):
    import db
    with db.conectar() as con:
        return con.execute(sa.select(db.reserva_saldo).where(db.reserva_saldo.c.cliente == cliente)).all()


def _flashes(c):
    with c.session_transaction() as s:
        return [m for _cat, m in s.get("_flashes", [])]


# --- describir referencias y sugerir sonido (Claude dentro de la petición) ---------------------

def _describir_falso(libro, vistas):
    def describir(refs, cliente_hint="", idioma="es", on_usage=None):
        vistas.append(libro.reservado("acme"))
        on_usage(USO)
        return "Una mujer gira el espejo"
    return describir


def test_describir_referencias_sin_saldo_no_llama_a_claude(app_crear, libro, monkeypatch):
    import referencias_link
    vistas = []
    monkeypatch.setattr(referencias_link, "describir", _describir_falso(libro, vistas))
    _cobra(libro)
    r = app_crear["c"].post("/cliente/acme/flowplus/describir", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 402 and r.get_json()["saldo_insuficiente"] is True
    assert vistas == [] and _gastos() == [] and _gastos("_creatv") == []


def test_describir_referencias_cobra_al_proyecto_con_reserva(app_crear, libro, monkeypatch):
    import gastos
    import referencias_link
    vistas = []
    monkeypatch.setattr(referencias_link, "describir", _describir_falso(libro, vistas))
    _cobra(libro, milesimas=5_000)
    r = app_crear["c"].post("/cliente/acme/flowplus/describir", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200 and r.get_json()["texto"] == "Una mujer gira el espejo"
    esperado = libro.precio_milesimas(gastos.estimar("describir_referencias", imagenes=1)["usd"], 1.5)
    assert vistas == [esperado] and _reservas() == []              # reservó mientras Claude miraba; ya se soltó
    g, = _gastos()
    assert g["tipo"] == "describir_referencias" and g["usd"] == 0.003 and g["proveedor"] == "anthropic"
    assert _gastos("_creatv") == []
    assert [m["milesimas"] for m in _movimientos() if m["tipo"] == "cobro"] == [-5]   # 0,003 × 1,5 → 4,5 → 5


def test_la_bandeja_muestra_el_precio_de_describir(app_crear, libro):
    import gastos
    _cobra(libro, milesimas=5_000)
    html = app_crear["c"].get("/cliente/acme").get_data(as_text=True)
    texto = gastos.formatear(round(gastos.estimar("describir_referencias", imagenes=1)["usd"] * 1.5, 4))
    assert 'id="fp-describir"' in html and texto in html


def test_contar_las_imagenes_que_se_describen():
    import referencias_link
    refs = [{"tipo": "imagen", "url": f"https://x/{i}.png", "etiqueta": f"@Imagen {i}"} for i in range(20)]
    assert referencias_link.imagenes_a_describir(refs[:3]) == 3
    assert referencias_link.imagenes_a_describir(refs) == 16                    # el tope de describir
    assert referencias_link.imagenes_a_describir([{"tipo": "video", "url": "https://x/v.mp4", "ruta_local": None}]) == 1
    assert referencias_link.imagenes_a_describir([]) == 0


def test_sugerir_sonido_sin_saldo_no_llama_a_claude(app_crear, libro, monkeypatch):
    from final_edition import sonido
    llamadas = []
    monkeypatch.setattr(sonido, "sugerir_descripcion", lambda *a, **k: llamadas.append(a) or "olas")
    _cobra(libro)
    r = app_crear["c"].post("/cliente/acme/creative_flow/sugerir_sonido", json={"escena": "una playa"})
    assert r.status_code == 402 and llamadas == [] and _gastos() == []


def test_sugerir_sonido_cobra_al_proyecto_con_reserva(app_crear, libro, monkeypatch):
    from final_edition import sonido
    vistas = []

    def sugerir(escena, enfoque, persona=None, idioma="es", on_usage=None):
        vistas.append(libro.reservado("acme"))
        on_usage(USO)
        return "olas, gaviotas"
    monkeypatch.setattr(sonido, "sugerir_descripcion", sugerir)
    _cobra(libro, milesimas=5_000)
    r = app_crear["c"].post("/cliente/acme/creative_flow/sugerir_sonido", json={"escena": "una playa"})
    assert r.status_code == 200 and r.get_json()["sonido"] == "olas, gaviotas"
    assert vistas and vistas[0] > 0 and _reservas() == []
    g, = _gastos()
    assert g["tipo"] == "sugerir_sonido" and _gastos("_creatv") == []
    assert any(m["tipo"] == "cobro" for m in _movimientos())


def test_un_proyecto_que_no_cobra_anota_la_ayuda_a_su_gasto_sin_frenar(app_crear, libro, monkeypatch):
    """«Todo se le cobra al cliente»: aunque no cobre, el gasto es del proyecto (no de `_creatv`)."""
    import referencias_link
    monkeypatch.setattr(referencias_link, "describir", _describir_falso(libro, []))
    r = app_crear["c"].post("/cliente/acme/flowplus/describir", headers={"X-Requested-With": "fetch"})
    assert r.status_code == 200
    assert [g["tipo"] for g in _gastos()] == ["describir_referencias"] and _gastos("_creatv") == []
    assert _movimientos() == []


# --- analizar marca (Claude en un hilo de la petición) ------------------------------------------

@pytest.fixture()
def marca_app(app_crear, monkeypatch):
    import dashboard
    import marca
    import trabajos
    guardado = {}
    monkeypatch.setattr(dashboard, "_marca_referencias", lambda c: [{"url": "https://r2/m1.jpg"}, {"url": "https://r2/m2.jpg"}])
    monkeypatch.setattr(marca, "cargar", lambda c: dict(guardado))
    monkeypatch.setattr(marca, "guardar", lambda c, data: guardado.update(data))
    iniciados = []
    monkeypatch.setattr(trabajos, "iniciar",
                        lambda job_id, fn, duracion_estimada=60, etapas=None, cliente=None: iniciados.append(fn) or True)
    return {**app_crear, "iniciados": iniciados, "guardado": guardado}


def test_analizar_marca_sin_saldo_no_lanza_nada(marca_app, libro):
    _cobra(libro)
    r = marca_app["c"].post("/cliente/acme/marca/analizar", headers=MISMO)
    assert r.status_code == 302 and marca_app["iniciados"] == []
    assert any("Saldo insuficiente" in m for m in _flashes(marca_app["c"]))


def test_analizar_marca_reserva_cobra_y_anota_su_gasto(marca_app, libro, monkeypatch):
    import generador_prompts
    vistas = []

    def analizar(urls, idioma="es", on_usage=None):
        vistas.append(libro.reservado("acme"))
        on_usage(USO)
        return "Paleta cálida, luz de atardecer."
    monkeypatch.setattr(generador_prompts, "analizar_marca", analizar)
    _cobra(libro, milesimas=5_000)
    r = marca_app["c"].post("/cliente/acme/marca/analizar", headers=MISMO)
    assert r.status_code == 302 and len(marca_app["iniciados"]) == 1
    assert len(_reservas()) == 1                                    # reservado mientras el hilo no termina
    marca_app["iniciados"][0]()
    assert marca_app["guardado"]["guia_estilo"] == "Paleta cálida, luz de atardecer."
    assert vistas and vistas[0] > 0 and _reservas() == []
    g, = _gastos()
    assert g["tipo"] == "analizar_marca" and g["usd"] == 0.003 and _gastos("_creatv") == []
    assert any(m["tipo"] == "cobro" for m in _movimientos())


def test_analizar_marca_anota_lo_que_cobro_claude_aunque_la_respuesta_no_sirva(monkeypatch):
    """`generador_prompts.analizar_marca` avisa el uso apenas Claude responde, antes de leer el texto."""
    import generador_prompts

    class _Cliente:
        def __init__(self, **k):
            self.messages = self

        def create(self, **k):
            return SimpleNamespace(usage=USO, content=[])
    monkeypatch.setattr(generador_prompts.anthropic, "Anthropic", _Cliente)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")  # llave-de-prueba
    usos = []
    with pytest.raises(generador_prompts.RespuestaInvalida):        # vacía: ni se guarda ni se cobra
        generador_prompts.analizar_marca(["https://r2/m1.jpg"], on_usage=usos.append)
    assert usos == [USO]


def test_analizar_marca_pide_un_tope_amplio(monkeypatch):
    """PND-342 (regla 7): con `max_tokens` 400 el pensamiento adaptativo podía dejar la guía vacía o cortada y cobrada.
    El tope es de 4 000 como mínimo (se paga solo lo usado)."""
    import generador_prompts
    pedidos = []

    class _Cliente:
        def __init__(self, **k):
            self.messages = self

        def create(self, **k):
            pedidos.append(k)
            return SimpleNamespace(usage=USO, stop_reason="end_turn",
                                   content=[SimpleNamespace(type="text", text="Paleta cálida.")])
    monkeypatch.setattr(generador_prompts.anthropic, "Anthropic", _Cliente)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-prueba")  # llave-de-prueba
    assert generador_prompts.analizar_marca(["https://r2/m1.jpg"]) == "Paleta cálida."
    assert pedidos[0]["max_tokens"] >= 4000


def test_el_precio_de_analizar_marca_cubre_lo_medido():
    """PND-342: el precio que se ve antes no queda por debajo del caso más caro medido el 2026-10-15 (cinco imágenes
    grandes: 21 528 de entrada y 349 de salida, US$ 0,0465; docs/superpowers/evals/2026-10-15-analizar-marca-4000.md).
    Antes era 0,025: cinco imágenes ya costaban más que el precio a la vista."""
    import gastos
    assert gastos.TARIFAS["analizar_marca"] >= 0.0465
    assert gastos.estimar("analizar_marca")["usd"] >= 0.0465


def test_analizar_marca_vacia_o_cortada_no_cobra_ni_pisa_la_guia(marca_app, libro, monkeypatch):
    """guardian-gasto 2026-10-15: con `max_tokens` 400, una respuesta cortada se cobraba y pisaba la guía buena."""
    import generador_prompts
    marca_app["guardado"]["guia_estilo"] = "La guía buena"

    def analizar(urls, idioma="es", on_usage=None):
        on_usage(USO)
        raise generador_prompts.RespuestaInvalida("cortada")
    monkeypatch.setattr(generador_prompts, "analizar_marca", analizar)
    _cobra(libro, milesimas=5_000)
    marca_app["c"].post("/cliente/acme/marca/analizar", headers=MISMO)
    with pytest.raises(generador_prompts.RespuestaInvalida):
        marca_app["iniciados"][0]()
    assert marca_app["guardado"]["guia_estilo"] == "La guía buena" and _reservas() == []
    g, = _gastos()
    assert g["tipo"] == "analizar_marca"
    assert [m["tipo"] for m in _movimientos()] == ["ajuste", "no_cobrado"]


def test_la_seccion_de_marca_muestra_el_precio(app_crear, libro, monkeypatch):
    import dashboard
    import gastos
    monkeypatch.setattr(dashboard, "_marca_referencias", lambda c: [{"url": "https://r2/m1.jpg"}])
    _cobra(libro, milesimas=5_000)
    html = app_crear["c"].get("/cliente/acme").get_data(as_text=True)
    assert gastos.formatear(round(gastos.TARIFAS["analizar_marca"] * 1.5, 4)) in html


# --- el director («Crear super prompt» y «Rearmar») ---------------------------------------------

def test_crear_super_prompt_sin_saldo_no_crea_la_sesion(app_crear, libro):
    import creative_flow as cf
    _cobra(libro)
    r = _crear(app_crear)
    assert r.status_code == 302 and cf.cargar("acme") == {} and app_crear["encolados"] == []
    assert any("Saldo insuficiente" in m for m in _flashes(app_crear["c"]))


def test_crear_super_prompt_encola_el_director_con_su_precio(app_crear, libro):
    import gastos
    _cobra(libro, milesimas=5_000)
    _crear(app_crear)
    t, = app_crear["encolados"]
    assert t["tipo"] == "flowplus_director" and t["costo_estimado"] == gastos.estimar("director")["usd"] > 0


def test_si_la_reserva_del_director_falla_la_sesion_queda_en_error(app_crear, libro, monkeypatch):
    """Otro clic se llevó el saldo entre el freno de la ruta y el encolado: la sesión no queda colgada en
    `prompt_pendiente` sin trabajo."""
    import creative_flow as cf
    from cobros import SaldoInsuficiente
    _cobra(libro, milesimas=5_000)

    def sin_saldo(*a, **k):
        raise SaldoInsuficiente("acme", 75, 0)
    monkeypatch.setattr(app_crear["dashboard"].trabajos, "encolar", sin_saldo)
    r = _crear(app_crear)
    assert r.status_code == 302
    (cf_id, e), = cf.cargar("acme").items()
    assert e["estado"] == "error" and "Saldo insuficiente" in e["error"]


def test_rearmar_sin_saldo_no_cambia_nada(app_crear, libro):
    import creative_flow as cf
    _crear(app_crear)                                              # sin «Cobrar»: se crea
    (cf_id, _), = cf.cargar("acme").items()
    cf.actualizar("acme", cf_id, estado="prompt_listo", prompt_relleno="A")
    app_crear["encolados"].clear()
    _cobra(libro)
    r = app_crear["c"].post(f"/cliente/acme/creative_flow/{cf_id}/rearmar")
    assert r.status_code == 302 and app_crear["encolados"] == []
    assert cf.cargar("acme")[cf_id]["estado"] == "prompt_listo"


def test_rearmar_con_saldo_encola_con_su_precio(app_crear, libro):
    import creative_flow as cf
    import gastos
    _crear(app_crear)
    (cf_id, _), = cf.cargar("acme").items()
    cf.actualizar("acme", cf_id, estado="prompt_listo", prompt_relleno="A")
    app_crear["encolados"].clear()
    _cobra(libro, milesimas=5_000)
    app_crear["c"].post(f"/cliente/acme/creative_flow/{cf_id}/rearmar")
    t, = app_crear["encolados"]
    assert t["costo_estimado"] == gastos.estimar("director")["usd"]


def test_el_boton_del_director_dice_su_precio_y_ya_no_gratis(app_crear, libro):
    import gastos
    _cobra(libro, milesimas=5_000)
    html = app_crear["c"].get("/cliente/acme").get_data(as_text=True)
    boton = html[html.index('id="fp-armar"'):]
    boton = boton[:boton.index("</button>")]
    assert "gratis" not in boton and "No cuesta nada" not in boton
    assert gastos.formatear(round(gastos.TARIFAS["director"] * 1.5, 4)) in boton     # como gastos.precio


def test_el_director_es_un_tipo_que_cobra():
    import tareas
    assert "flowplus_director" in tareas.TIPOS_QUE_COBRAN and "flowplus_director" not in tareas.TIPOS_EXENTOS_DE_COBRO


# --- saldo de bienvenida --------------------------------------------------------------------------

def test_bienvenida_una_sola_vez_por_proyecto(libro):
    _cobra(libro)
    assert libro.bienvenida_usd() == 2.0
    assert libro.dar_bienvenida("acme", usuario="ana") == 2_000
    assert libro.dar_bienvenida("acme", usuario="ana") == 0                 # idempotente
    assert libro.dar_bienvenida("acme", usuario="beto") == 0                # otro usuario del mismo proyecto
    m, = _movimientos()
    assert (m["tipo"], m["concepto"], m["milesimas"]) == ("ajuste", "bienvenida", 2_000)
    assert libro.saldo("acme") == 2_000


def test_bienvenida_solo_a_un_proyecto_prepago_que_cobra(libro):
    assert libro.dar_bienvenida("acme") == 0                               # sin cuenta: no cobra
    libro.configurar("acme", usuario="admin", cobrar=False)
    assert libro.dar_bienvenida("acme") == 0                               # «Cobrar» apagado
    _cobra(libro, cliente="otro", pospago=True)
    assert libro.dar_bienvenida("otro") == 0                               # pospago: el regalo pagaría deuda
    assert _movimientos("acme") == [] and _movimientos("otro") == []


def test_el_valor_de_la_bienvenida_se_edita_y_cero_la_apaga(libro):
    _cobra(libro)
    _cobra(libro, cliente="otro")
    libro.guardar_bienvenida(3.5, "admin")
    assert libro.bienvenida_usd() == 3.5 and libro.dar_bienvenida("acme") == 3_500
    libro.guardar_bienvenida(0, "admin")
    assert libro.dar_bienvenida("otro") == 0 and _movimientos("otro") == []
    for malo in (-1, 20.01, float("nan")):
        with pytest.raises(ValueError):
            libro.guardar_bienvenida(malo, "admin")
    assert libro.bienvenida_usd() == 0


def test_la_bienvenida_tiene_nombre_en_el_libro(libro):
    from cobros import vista
    assert vista.nombre_concepto("bienvenida", "ajuste") == "Saldo de bienvenida"


def test_confirmar_correo_da_la_bienvenida_al_proyecto_de_la_cuenta(libro, usuarios_tmp):
    import cuentas
    usuarios_tmp.crear("ana", "secreta123", "cliente", cliente="acme", correo="ana@ejemplo.com")
    _cobra(libro)
    entry, regalo = cuentas.confirmar_correo("ana")
    assert entry["correo_verificado"] is True and regalo == 2_000 and libro.saldo("acme") == 2_000
    usuarios_tmp.actualizar("ana", correo_verificado=False)                # cambia de correo y lo vuelve a confirmar
    assert cuentas.confirmar_correo("ana", correo="ana2@ejemplo.com")[1] == 0
    assert libro.saldo("acme") == 2_000


def test_confirmar_correo_de_un_admin_no_regala_nada(libro, usuarios_tmp):
    import cuentas
    _cobra(libro)
    assert cuentas.confirmar_correo("admin")[1] == 0 and _movimientos() == []


def test_si_regalar_falla_la_verificacion_igual_queda(libro, usuarios_tmp, monkeypatch):
    import cuentas
    usuarios_tmp.crear("ana", "secreta123", "cliente", cliente="acme", correo="ana@ejemplo.com")
    monkeypatch.setattr(libro, "dar_bienvenida", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("base caída")))
    entry, regalo = cuentas.confirmar_correo("ana")
    assert entry["correo_verificado"] is True and regalo == 0


def test_bienvenida_no_a_un_proyecto_que_ya_tuvo_saldo(libro):
    """«Cada proyecto nuevo»: uno que ya recargó (o al que el admin ya le dio el regalo a mano con un ajuste) no lo
    recibe al verificar una cuenta."""
    _cobra(libro, milesimas=10_000)                                        # un ajuste a favor
    assert libro.dar_bienvenida("acme") == 0
    import db
    _cobra(libro, cliente="otro")
    with db.conectar() as con:
        libro.acreditar(con, "otro", "recarga", 10_000, "recarga_manual", usuario="admin")
    assert libro.dar_bienvenida("otro") == 0


def test_bienvenida_una_vez_por_buzon_aunque_cambie_el_alias(libro):
    """guardian-gasto 2026-10-15: con un Gmail y `+1`, `+2`… cada proyecto nuevo sacaba US$ 2."""
    assert libro.correo_canonico("Ana.Gomez+2@GMail.com") == "anagomez@gmail.com"
    assert libro.correo_canonico("ana+x@empresa.co") == "ana@empresa.co"
    _cobra(libro, cliente="p1")
    _cobra(libro, cliente="p2")
    _cobra(libro, cliente="p3")
    assert libro.dar_bienvenida("p1", correo="ana.gomez+1@gmail.com") == 2_000
    assert libro.dar_bienvenida("p2", correo="anagomez+2@googlemail.com") == 0
    assert libro.dar_bienvenida("p3", correo="otra@gmail.com") == 2_000
