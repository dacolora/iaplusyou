"""
Prueba de carga con Locust (spec 2026-10-01-escala-y-monitoreo §7): N personas
a la vez usando la plataforma como se usa de verdad, cada una en su proyecto.

Cada usuario simulado entra con su cuenta (`carga01`, `carga02`, … del
sembrador, contraseña `carga-1234`) y luego: abre la página de su proyecto,
sondea las barras de progreso que esa página trae (el navegador lo hace solo
cada 1,5–5 s), pide «Ver más» de Crear, abre el detalle de una pieza y la
galería del catálogo. Dos ritmos (CARGA_RITMO):

- `realista` (por defecto): una persona activa — una acción cada 3–8 s, casi
  siempre el sondeo; un detalle cada ~45 s; recarga la página cada ~2–3 min.
- `estres`: una acción cada 2–6 s y muchas pesadas (página, «Ver más»,
  detalle): 100 personas así son ~10 acciones pesadas por segundo.

    # 1) datos (en una COPIA del repo, nunca en producción):
    venv/bin/python3 -m rendimiento.sembrar --proyectos 10 --piezas 300
    # 2) la app como en el VPS:
    venv/bin/gunicorn -c deploy/gunicorn.conf.py dashboard:app
    # 3) 100 usuarios, 10 nuevos por segundo, 3 minutos (CARGA_RITMO=estres para el ritmo duro):
    venv/bin/locust -f rendimiento/locustfile.py --headless -u 100 -r 10 -t 3m \\
        --host http://127.0.0.1:5050 --csv data/carga

Contra otra máquina que no sea esta se niega (crearía sesiones y carga real
sobre clientes reales) salvo con CARGA_PERMITIR_REMOTO=1 — y entonces solo
contra un servidor de pruebas sembrado, nunca contra app.creatvmachine.com.
Variables: CARGA_PROYECTOS (10), CARGA_PREFIJO (carga), CARGA_PASSWORD.
"""
import itertools
import os
import random
import re
from urllib.parse import urlsplit

from locust import HttpUser, between, events, task

RITMO = "estres" if os.environ.get("CARGA_RITMO") == "estres" else "realista"
PROYECTOS = int(os.environ.get("CARGA_PROYECTOS") or 10)
PREFIJO = os.environ.get("CARGA_PREFIJO") or "carga"
PASSWORD = os.environ.get("CARGA_PASSWORD") or "carga-1234"
HOSTS_LOCALES = ("localhost", "127.0.0.1", "::1")
_turno = itertools.count()
_BARRA = re.compile(r'data-poll-job="([^"]+)"')
_DETALLE = re.compile(r'data-detalle="([^"]+/creative_flow/[^"]+/detalle)"')


@events.test_start.add_listener
def _solo_local(environment, **_):
    host = (urlsplit(environment.host or "").hostname or "").lower()
    if host not in HOSTS_LOCALES and os.environ.get("CARGA_PERMITIR_REMOTO") != "1":
        print(f"[carga] {environment.host} no es esta máquina: no se prueba (CARGA_PERMITIR_REMOTO=1 para forzar).")
        environment.runner.quit()


# Peso de cada acción (cuántas veces, de cada 20 o 26 turnos, toca esa).
PESOS = {"realista": {"abrir_proyecto": 1, "sondear_barras": 20, "ver_mas_crear": 1, "detalle_de_una_pieza": 3,
                      "catalogo": 1},
         "estres": {"abrir_proyecto": 3, "sondear_barras": 12, "ver_mas_crear": 2, "detalle_de_una_pieza": 2,
                    "catalogo": 1}}[RITMO]


class PersonaEnSuProyecto(HttpUser):
    wait_time = between(3, 8) if RITMO == "realista" else between(2, 6)

    def on_start(self):
        n = next(_turno) % PROYECTOS + 1
        self.proyecto = f"{PREFIJO}{n:02d}"
        self.barras, self.detalles = [], []
        self.client.get("/login", name="/login")
        r = self.client.post("/login", data={"usuario": self.proyecto, "password": PASSWORD},
                             allow_redirects=False, name="/login [POST]")
        if r.status_code != 302:
            raise RuntimeError(f"no pude entrar como {self.proyecto}: {r.status_code}")
        self.abrir_proyecto()

    @task(PESOS["abrir_proyecto"])
    def abrir_proyecto(self):
        r = self.client.get(f"/cliente/{self.proyecto}", name="/cliente/[proyecto]")
        if r.ok:
            self.barras = sorted(set(_BARRA.findall(r.text)))[:6]
            self.detalles = _DETALLE.findall(r.text)[:24]

    @task(PESOS["sondear_barras"])
    def sondear_barras(self):
        for job in self.barras:
            self.client.get(f"/trabajo/{job}/estado", name="/trabajo/[job]/estado")

    @task(PESOS["ver_mas_crear"])
    def ver_mas_crear(self):
        self.client.get(f"/cliente/{self.proyecto}/crear/tarjetas?desde=24", name="/cliente/[proyecto]/crear/tarjetas")

    @task(PESOS["detalle_de_una_pieza"])
    def detalle_de_una_pieza(self):
        if self.detalles:
            self.client.get(random.choice(self.detalles), name="/cliente/[proyecto]/creative_flow/[cf]/detalle")

    @task(PESOS["catalogo"])
    def catalogo(self):
        self.client.get(f"/cliente/{self.proyecto}/catalogo/grid", name="/cliente/[proyecto]/catalogo/grid")
