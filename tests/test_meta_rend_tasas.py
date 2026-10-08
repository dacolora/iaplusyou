"""USD por día (spec §7): BCE por frankfurter, fines de semana con el último día
publicado, USD = 1 sin pedir nada, y sin tasa = None (nunca inventada)."""
from datetime import date

from meta_rendimiento import tasas


class _Resp:
    def __init__(self, datos, status=200):
        self.status_code, self._d = status, datos

    def json(self):
        return self._d

    def close(self):
        pass


def test_stored_rates_no_exception_no_refetch(base_temporal, monkeypatch, caplog):
    """Dos tasas SEK guardadas, reset cache, llamada otra vez → 0 requests, NO exception."""
    tasas._reiniciar_cache()
    pedidas = []

    # Primera llamada: fetch y guarda dos tasas
    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-02": {"USD": 0.10}, "2026-10-05": {"USD": 0.11}}})
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-02", "2026-10-05", hoy=date(2026, 10, 5))
    assert len(pedidas) == 1

    # Reset cache pero NO reset DB → tasas ya guardadas
    tasas._reiniciar_cache()
    pedidas.clear()

    # Segunda llamada con mismo rango → debe usar datos guardados, 0 requests, NO exception
    tasas.asegurar(["SEK"], "2026-10-02", "2026-10-05", hoy=date(2026, 10, 5))
    assert len(pedidas) == 0  # No new request
    assert "TypeError" not in caplog.text


def test_holiday_inside_range_no_refetch(base_temporal, monkeypatch, caplog):
    """Festivo dentro (25/26 Dec missing): tasas 22,23,24,29,30 Dec, rango 22..30 Dec, hoy=2027-01-05
    → objetivo=30 Dec (Wed), segunda llamada 0 requests."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        # Rates: 22 (Tue), 23 (Wed), 24 (Thu), 29 (Tue), 30 (Wed)
        return _Resp({"base": "SEK", "rates": {
            "2026-12-22": {"USD": 0.10}, "2026-12-23": {"USD": 0.11}, "2026-12-24": {"USD": 0.12},
            "2026-12-29": {"USD": 0.13}, "2026-12-30": {"USD": 0.14}
        }})
    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    # Primera llamada: 22-30 Dec, hoy=2027-01-05
    # hasta=2026-12-30 < hoy, objetivo = _last_weekday(2026-12-30) = 2026-12-30 (Wed, weekday=2)
    tasas.asegurar(["SEK"], "2026-12-22", "2026-12-30", hoy=date(2027, 1, 5))
    assert len(pedidas) == 1

    # Segunda llamada: mismo rango
    # objetivo=2026-12-30, inicio=min(_last_weekday(2026-12-22), objetivo)=min(2026-12-22, 2026-12-30)=2026-12-22
    # ya tiene 22,23,24,29,30; tiene_antes_inicio (22<=22)✓, tiene_objetivo (30>=30)✓ → skip
    tasas.asegurar(["SEK"], "2026-12-22", "2026-12-30", hoy=date(2027, 1, 5))
    assert len(pedidas) == 1  # No new request
    assert "TypeError" not in caplog.text


def test_one_day_range_old_cached_must_fetch(base_temporal, monkeypatch, caplog):
    """Rango un día (lun 5 oct, hoy 8 oct) con solo 1-2 oct cached → fetches."""
    tasas._reiniciar_cache()
    pedidas = []

    # Pre-cache 1-2 Oct
    def abrir_precache(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-01": {"USD": 0.10}, "2026-10-02": {"USD": 0.11}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir_precache)
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 8))
    assert len(pedidas) == 1

    # Segunda llamada: rango 5 oct, hoy 8 oct
    # objetivo = _last_weekday(2026-10-05) = 2026-10-05 (Mon, weekday=0)
    # inicio = min(_last_weekday(2026-10-05), objetivo) = 2026-10-05
    # ya tiene 2026-10-01, 2026-10-02; tiene_antes_inicio (2026-10-02 <= 2026-10-05)✓
    # tiene_objetivo (max=2026-10-02 >= 2026-10-05)? NO → must fetch

    def abrir_new(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-05": {"USD": 0.12}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir_new)
    tasas.asegurar(["SEK"], "2026-10-05", "2026-10-05", hoy=date(2026, 10, 8))
    assert len(pedidas) == 2  # New request made
    assert "TypeError" not in caplog.text


def test_past_range_complete_data_no_refetch(base_temporal, monkeypatch, caplog):
    """Rango pasado con datos completos hasta objetivo → sin refetch."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        # Retorna ambos 1 Oct (Thu) y 2 Oct (Fri), completando objetivo
        return _Resp({"base": "SEK", "rates": {"2026-10-01": {"USD": 0.10}, "2026-10-02": {"USD": 0.11}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-03", hoy=date(2026, 10, 5))
    assert len(pedidas) == 1

    # Segunda llamada: hasta=2026-10-03 < hoy=2026-10-05, objetivo=_last_weekday(2026-10-03)=2026-10-02
    # inicio = min(2026-10-01, 2026-10-02) = 2026-10-01
    # ya tiene 2026-10-01, 2026-10-02; tiene_antes_inicio ✓, tiene_objetivo (2026-10-02>=2026-10-02) ✓
    # → skip

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-03", hoy=date(2026, 10, 5))
    assert len(pedidas) == 1  # No new request
    assert "TypeError" not in caplog.text


def test_today_only_range_empty_table_must_fetch(base_temporal, monkeypatch, caplog):
    """Rango hoy-only con tabla vacía → fetches."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        # Retorna rate de ayer (para forward-fill a hoy)
        return _Resp({"base": "SEK", "rates": {"2026-10-07": {"USD": 0.10}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    # desde = hasta = hoy, tabla vacía
    # hoy=2026-10-08, hasta=2026-10-08, hasta >= hoy → check_date = hoy-1 = 2026-10-07
    # objetivo = _last_weekday(2026-10-07) = 2026-10-07 (Thu, weekday=3)
    # inicio = min(_last_weekday(2026-10-08), objetivo) = min(2026-10-08, 2026-10-07) = 2026-10-07
    # ya está vacío → must fetch
    tasas.asegurar(["SEK"], "2026-10-08", "2026-10-08", hoy=date(2026, 10, 8))
    assert len(pedidas) == 1  # Must fetch
    assert "TypeError" not in caplog.text


def test_non_dict_json_body_no_exception(base_temporal, monkeypatch):
    """Body no-dict (list) no lanza excepción."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp([1, 2])  # JSON list, not dict

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    # Nunca lanza
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert tasas.mapa("SEK", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}


def test_rates_list_not_dict_no_exception(base_temporal, monkeypatch):
    """rates como lista en lugar de dict no lanza excepción."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp({"rates": [1, 2]})  # rates es lista

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert tasas.mapa("SEK", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}


def test_non_numeric_rate_skips_date(base_temporal, monkeypatch):
    """Tasa no-numérica skips ese día, no lanza excepción."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp({"rates": {"2026-10-01": {"USD": "abc"}, "2026-10-02": {"USD": 0.10}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    m = tasas.mapa("SEK", "2026-10-01", "2026-10-02")
    # 1 Oct: tasa inválida → None; 2 Oct: tasa válida → 0.10
    assert m == {"2026-10-01": None, "2026-10-02": 0.10}


def test_404_no_refetch_6h(base_temporal, monkeypatch):
    """404 → segunda llamada dentro de 6h hace 0 requests, mapa da None."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({}, status=404)

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["COP"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert len(pedidas) == 1

    # Segunda llamada: dentro de 6h → no vuelve a pedir
    tasas.asegurar(["COP"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 2))
    assert len(pedidas) == 1

    # mapa da None
    assert tasas.mapa("COP", "2026-10-01", "2026-10-02") == {"2026-10-01": None, "2026-10-02": None}


def test_usd_always_one(base_temporal, monkeypatch):
    """USD siempre retorna 1.0, sin pedir nada."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["USD"], "2026-10-01", "2026-10-02")
    assert len(pedidas) == 0  # USD never requests
    assert tasas.mapa("USD", "2026-10-01", "2026-10-02") == {"2026-10-01": 1.0, "2026-10-02": 1.0}
