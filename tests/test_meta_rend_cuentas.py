"""Cuentas que un proyecto lee (spec §5): país adivinado por el nombre, una
cuenta en un solo proyecto, quitar borra sus copias."""
from meta_rendimiento import cuentas

HF = [{"id": "act_709406360806038", "name": "HappyFlops Norway", "currency": "SEK"},
      {"id": "act_883891256188845", "name": "HappyFlops Netherlands (Active)", "currency": "SEK"},
      {"id": "act_708698354181244", "name": "HappyFlops World Wide", "currency": "SEK"},
      {"id": "act_228061763662782", "name": "HappyFlops MX", "currency": "SEK"},
      {"id": "act_1236343913931133", "name": "HappyFlops Poland (old DK)", "currency": "SEK"},
      {"id": "act_335308812712423", "name": "HappyFlops Finland 2025", "currency": "SEK"}]


def test_adivinar_pais_por_nombre():
    esperado = ["NO", "NL", None, "MX", "PL", "FI"]
    assert [cuentas.adivinar_pais(c["name"]) for c in HF] == esperado
    assert cuentas.adivinar_pais("HappyFlops Sweden") == "SE"
    assert cuentas.adivinar_pais("") is None


def test_adivinar_pais_no_confunde_palabras_pegadas_ni_cola():
    # Nombres sin país no pueden dar uno por unir palabras («WorldWide», «HappyFlops») ni por
    # «Active»/«old»; y un país pegado a la marca sigue sin adivinarse (solo palabras sueltas).
    for nombre in ("WorldWide", "HappyFlops", "HappyFlops Active", "HappyFlops (old)", "Flops World Wide Active old",
                   None, "   ", "2025"):
        assert cuentas.adivinar_pais(nombre) is None, nombre
    assert cuentas.adivinar_pais("HappyFlops Sweden (Active)") == "SE"
    assert cuentas.adivinar_pais("happyflops mx") is None    # el código ISO suelto pide mayúsculas


def test_normalizar_id():
    assert cuentas.normalizar_id("123") == "act_123" and cuentas.normalizar_id("act_123") == "act_123"


def test_elegir_reemplaza_y_rechaza_cuentas_de_otro_proyecto(base_temporal, monkeypatch):
    borradas = []
    monkeypatch.setattr(cuentas, "_borrar_copias", lambda c, a: borradas.append((c, a)))
    r = cuentas.elegir("happyflops", [dict(c, pais=cuentas.adivinar_pais(c["name"])) for c in HF[:3]], usuario="admin")
    assert sorted(r["agregadas"]) == sorted(c["id"] for c in HF[:3]) and not r["rechazadas"]
    assert {c["ad_account_id"]: c["pais"] for c in cuentas.listar("happyflops")}["act_709406360806038"] == "NO"
    r = cuentas.elegir("otro", [HF[0], HF[3]])
    assert r["rechazadas"] == ["act_709406360806038"] and r["agregadas"] == ["act_228061763662782"]
    assert cuentas.dueno("act_709406360806038") == "happyflops"
    r = cuentas.elegir("happyflops", [HF[0]])
    assert sorted(r["quitadas"]) == sorted(["act_883891256188845", "act_708698354181244"])
    assert ("happyflops", "act_883891256188845") in borradas
    assert cuentas.ids("happyflops") == ["act_709406360806038"]
    assert sorted(cuentas.todas()) == [("happyflops", "act_709406360806038"), ("otro", "act_228061763662782")]


def test_pais_invalido_se_guarda_vacio_y_cambiar_pais(base_temporal):
    cuentas.elegir("acme", [dict(HF[0], pais="ZZ")])
    assert cuentas.cuenta("acme", "act_709406360806038")["pais"] is None
    assert cuentas.cambiar_pais("acme", "act_709406360806038", "no")
    assert cuentas.cuenta("acme", "act_709406360806038")["pais"] == "NO"
    assert not cuentas.cambiar_pais("acme", "act_999", "NO")


def test_actualizar_extra_mezcla(base_temporal):
    cuentas.elegir("acme", [HF[0]])
    cuentas.actualizar_extra("acme", "act_709406360806038", {"a": 1})
    cuentas.actualizar_extra("acme", "act_709406360806038", {"b": 2})
    assert cuentas.cuenta("acme", "act_709406360806038")["extra"] == {"a": 1, "b": 2}


def test_elegir_idempotente_conserva_lo_ya_copiado_y_acepta_ids_sin_prefijo(base_temporal, monkeypatch):
    borradas = []
    monkeypatch.setattr(cuentas, "_borrar_copias", lambda c, a: borradas.append((c, a)))
    cuentas.elegir("acme", [HF[0]])
    cuentas.actualizar("acme", "709406360806038", estado="ok", ultima_copia="2026-10-08 10:00:00",
                       moneda="NOK", inventado="no se guarda")
    # Elegir de nuevo la misma cuenta (sin «act_») no la toca, ni la agrega, ni borra copias.
    r = cuentas.elegir("acme", [{"id": "709406360806038", "name": "Otro nombre", "currency": "EUR"}])
    assert r == {"agregadas": [], "quitadas": [], "rechazadas": []} and not borradas
    c = cuentas.cuenta("acme", "act_709406360806038")
    assert (c["estado"], c["moneda"], c["nombre"]) == ("ok", "NOK", "HappyFlops Norway")
    assert c["ultima_copia"] == "2026-10-08 10:00:00" and "inventado" not in c
    # Una selección vacía (o con entradas sin id) quita todas las del proyecto.
    r = cuentas.elegir("acme", [{"name": "sin id"}])
    assert r["quitadas"] == ["act_709406360806038"] and cuentas.ids("acme") == []
    assert borradas == [("acme", "act_709406360806038")]


def test_la_carrera_por_la_misma_cuenta_la_rechaza_el_indice(base_temporal, monkeypatch):
    # Otro proyecto la tomó entre el chequeo y el insert: el índice único responde y va a rechazadas.
    monkeypatch.setattr(cuentas, "_borrar_copias", lambda c, a: None)
    cuentas.elegir("happyflops", [HF[0]])
    monkeypatch.setattr(cuentas, "dueno", lambda act: None)
    r = cuentas.elegir("otro", [HF[0]])
    assert r == {"agregadas": [], "quitadas": [], "rechazadas": ["act_709406360806038"]}
    assert cuentas.ids("otro") == []


def test_listar_ordena_por_nombre_y_aisla_proyectos(base_temporal, monkeypatch):
    monkeypatch.setattr(cuentas, "_borrar_copias", lambda c, a: None)
    cuentas.elegir("acme", [HF[3], HF[0], HF[1]])
    cuentas.elegir("otro", [HF[2]])
    assert [c["nombre"] for c in cuentas.listar("acme")] == [
        "HappyFlops MX", "HappyFlops Netherlands (Active)", "HappyFlops Norway"]
    assert cuentas.ids("otro") == ["act_708698354181244"]
    assert cuentas.listar("nadie") == [] and cuentas.cuenta("acme", "act_708698354181244") is None
    # Una cuenta de otro proyecto no se puede editar desde éste.
    assert not cuentas.cambiar_pais("acme", "act_708698354181244", "SE")
    cuentas.actualizar("acme", "act_708698354181244", estado="error")
    cuentas.actualizar_extra("acme", "act_708698354181244", {"x": 1})
    otra = cuentas.cuenta("otro", "act_708698354181244")
    assert otra["estado"] == "nueva" and otra["extra"] == {}
