"""Correos de la cuenta (spec 2026-09-26 §B8): salen en el idioma de la persona
a la que van, no en el de quien hace la petición."""
import re

import cuentas
import idiomas
from tests.i18n_util import _con_marca


def test_correo_en_el_idioma_de_la_persona(base_temporal, monkeypatch):
    enviados = []
    monkeypatch.setattr(cuentas, "smtp_configurado", lambda: True)
    monkeypatch.setattr(cuentas.notificaciones, "enviar",
                        lambda correo, asunto, cuerpo, html=None: enviados.append((asunto, cuerpo, html)) or True)
    idiomas.guardar_de_usuario("admin", "en")
    assert cuentas.enviar_restablecer("admin", "admin@prueba.local", "http://localhost")
    idiomas.guardar_de_usuario("admin", "es")
    assert cuentas.enviar_restablecer("admin", "admin@prueba.local", "http://localhost")
    (asunto_en, cuerpo_en, html_en), (asunto_es, cuerpo_es, html_es) = enviados
    assert "password" in asunto_en.lower() and "contraseña" in asunto_es.lower()
    assert '<html lang="en">' in html_en and '<html lang="es">' in html_es
    assert "1 hour" in cuerpo_en and "1 hora" in cuerpo_es
    # Regresión: cuentas.py:237 tenía gettext(...) dentro de las llaves de un
    # f-string, Babel nunca lo extraía y ese renglón le quedaba en español al
    # correo en inglés. Se saca el enlace (una URL, no texto) antes de mirar
    # marcas de español en el resto del cuerpo y del HTML; en el HTML también
    # se saca `lang="en"` (ya afirmado arriba), que si no dispara un falso
    # positivo: "en" es palabra de MARCAS igual que en español.
    enlace = re.search(r"http://\S+", cuerpo_en).group(0)
    assert not _con_marca(cuerpo_en.replace(enlace, "")), cuerpo_en
    html_en_sin_ruido = html_en.replace(enlace, "").replace('<html lang="en">', "<html>")
    assert not _con_marca(html_en_sin_ruido), html_en
