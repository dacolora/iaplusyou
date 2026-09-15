def test_paises_tienen_idioma_y_moneda():
    from final_edition import tipos
    for c in ("CO", "MX", "US", "ES", "BR"):
        p = tipos.PAISES[c]
        assert p["idioma"] in ("es", "en", "pt") and len(p["moneda"]) == 3


def test_formatear_precio():
    from final_edition import tipos
    assert tipos.formatear_precio(89900, "CO") == "$ 89.900"
    assert tipos.formatear_precio(89.9, "US") == "$89.90"
    assert tipos.formatear_precio(89.9, "BR") == "R$ 89,90"


def _guion(dur=10):
    roles = ("hook", "problema", "producto", "prueba", "cta")
    return {"idioma": "es", "pais": "CO", "moneda": "COP", "precio_texto": None,
            "bloques": [{"rol": r, "texto_pantalla": r.upper(), "texto_voz": f"voz {r}", "inicio_s": i * 2.0, "fin_s": i * 2.0 + 2.0} for i, r in enumerate(roles)]}


def test_validar_guion_ok():
    from final_edition import tipos
    assert tipos.validar_guion(_guion(), 10.0) == []


def test_validar_guion_errores():
    from final_edition import tipos
    g = _guion(); g["bloques"][1]["rol"] = "hook"; g["bloques"][-1]["fin_s"] = 12.0
    errs = tipos.validar_guion(g, 10.0)
    assert any("rol" in e for e in errs) and any("duraci" in e for e in errs)


def test_fuentes_existen():
    import os
    from final_edition import tipos
    for ruta in tipos.FUENTES.values():
        assert os.path.isfile(ruta) and ruta.endswith(".ttf")


def test_paises_tienen_bandera():
    from final_edition import tipos
    for c, p in tipos.PAISES.items():
        assert p.get("bandera"), f"{c} sin bandera"
    assert tipos.PAISES["CO"]["bandera"] == "🇨🇴"
