"""USD por día (spec §7): BCE por frankfurter, fines de semana con el último día
publicado, USD = 1 sin pedir nada, y sin tasa = None (nunca inventada)."""
import json
from datetime import date

from meta_rendimiento import tasas


class _Resp:
    """Lo que de verdad devuelve `conectores.url.abrir`: una respuesta de requests abierta con stream=True, de la que
    el código lee con `iter_content` (nada de `.json()`, que bajaría el cuerpo entero sin tope). `datos` se serializa
    a JSON; `cuerpo` permite entregar bytes a mano (un cuerpo enorme o roto)."""

    def __init__(self, datos=None, status=200, cuerpo=None):
        self.status_code = status
        self._cuerpo = cuerpo if cuerpo is not None else json.dumps(datos).encode()
        self.cerrada = False

    def iter_content(self, chunk_size=1, decode_unicode=False):
        for i in range(0, len(self._cuerpo), chunk_size):
            yield self._cuerpo[i:i + chunk_size]

    def close(self):
        self.cerrada = True


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
    # objetivo=2026-12-30, inicio=min(_last_weekday(2026-12-22), objetivo)=2026-12-22
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


def test_past_range_stored_rate_older_than_objetivo_must_fetch(base_temporal, monkeypatch, caplog):
    """Rango pasado 1-3 oct (sáb) con solo la tasa del 1 oct guardada: el objetivo es el vie 2 oct
    (último laborable ≤ hasta) y lo guardado más nuevo (1 oct) lo deja atrás → pide, exactamente una vez.
    Mata la mutación `max(ya) >= inicio` (inicio = 1 oct la daría por completa y no pediría nada)."""
    tasas._reiniciar_cache()
    pedidas = []

    # Primera llamada: guarda SOLO la tasa del 1 oct (la respuesta del BCE aún no trae el 2)
    def abrir_solo_1(url, **_):
        pedidas.append(url)
        return _Resp({"base": "SEK", "rates": {"2026-10-01": {"USD": 0.10}}})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir_solo_1)
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-03", hoy=date(2026, 10, 8))
    assert len(pedidas) == 1
    assert tasas._guardadas("SEK", "2026-09-24", "2026-10-03") == {"2026-10-01": 0.10}

    # Sin caché negativo: solo lo guardado decide. Estado: ya={1 oct}, inicio=1 oct, objetivo=2 oct
    # tiene_antes_inicio (1<=1)✓, tiene_objetivo (max=1 oct >= 2 oct)? NO → must fetch
    tasas._reiniciar_cache()
    pedidas.clear()

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-03", hoy=date(2026, 10, 8))
    assert len(pedidas) == 1
    assert "TypeError" not in caplog.text


def test_past_range_complete_data_cache_independent(base_temporal, monkeypatch, caplog):
    """Prove stored rates drive skip: reset cache between calls so negative cache can't help."""
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
    # → skip (con el caché negativo reiniciado, solo lo guardado puede explicarlo)
    tasas._reiniciar_cache()
    pedidas.clear()

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-03", hoy=date(2026, 10, 5))
    assert len(pedidas) == 0  # No new request
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


def test_zero_and_negative_rates_not_stored(base_temporal, monkeypatch):
    """Tasas 0, negativas, NaN, Inf nunca se guardan."""
    tasas._reiniciar_cache()

    def abrir(url, **_):
        return _Resp({"rates": {
            "2026-10-01": {"USD": 0.0},
            "2026-10-02": {"USD": -0.05},
            "2026-10-03": {"USD": float('nan')},
            "2026-10-04": {"USD": float('inf')},
            "2026-10-05": {"USD": 0.10},
        }})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-05", hoy=date(2026, 10, 5))

    m = tasas.mapa("SEK", "2026-10-01", "2026-10-05")
    assert m == {"2026-10-01": None, "2026-10-02": None, "2026-10-03": None,
                 "2026-10-04": None, "2026-10-05": 0.10}


def test_none_values_not_raise(base_temporal, monkeypatch):
    """asegurar con argumentos inválidos (fechas None, monedas None, monedas que no son texto)
    no lanza: registra un aviso y no pide nada."""
    tasas._reiniciar_cache()
    pedidas = []

    def abrir(url, **_):
        pedidas.append(url)
        return _Resp({})

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], None, "2026-10-03")
    tasas.asegurar(None, "2026-10-01", "2026-10-03")
    tasas.asegurar([5], "2026-10-01", "2026-10-03")  # un elemento que no es texto se ignora
    assert pedidas == []


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


# --- ruling R24 (relleno de 4 días) y G2 (la respuesta del BCE se trata como ajena) --------------------------------

def _sembrar(moneda, tasas_por_fecha):
    import db
    with db.conectar() as con:
        for fecha, v in tasas_por_fecha.items():
            con.execute(db.tasa_cambio.insert().values(fecha=fecha, moneda=moneda, usd_por_unidad=v, fuente="bce",
                                                       creado_en=db.ahora()))


def test_weekend_filled_with_friday_rate(base_temporal):
    """Viernes 2 oct publicado; sábado, domingo y lunes sin publicar toman el del viernes."""
    _sembrar("SEK", {"2026-10-01": 0.09, "2026-10-02": 0.10})
    m = tasas.mapa("SEK", "2026-10-02", "2026-10-05")
    assert m == {"2026-10-02": 0.10, "2026-10-03": 0.10, "2026-10-04": 0.10, "2026-10-05": 0.10}


def test_gap_of_five_days_or_more_is_none(base_temporal):
    """Hasta 4 días después de la última tasa publicada se rellena; el quinto y siguientes son None."""
    _sembrar("SEK", {"2026-10-01": 0.10})
    m = tasas.mapa("SEK", "2026-10-01", "2026-10-08")
    assert [m[f"2026-10-0{d}"] for d in range(1, 6)] == [0.10] * 5      # el 1 y los 4 días siguientes
    assert [m[f"2026-10-0{d}"] for d in (6, 7, 8)] == [None] * 3        # 5, 6 y 7 días después
    assert tasas.usd("SEK", "2026-10-06") is None


def test_gap_counts_from_last_published_not_from_range_start(base_temporal):
    """La última publicada anterior al rango (en la holgura) cuenta: un rango que empieza 3 días después aún la usa,
    uno que empieza 5 días después ya no."""
    _sembrar("SEK", {"2026-09-30": 0.10})
    assert tasas.mapa("SEK", "2026-10-03", "2026-10-03") == {"2026-10-03": 0.10}
    assert tasas.mapa("SEK", "2026-10-05", "2026-10-05") == {"2026-10-05": None}


def test_body_over_1mb_is_ignored(base_temporal, monkeypatch, caplog):
    """Una respuesta de más de 1 MB no se guarda ni lanza: se corta la lectura, queda un aviso y no se re-pide."""
    tasas._reiniciar_cache()
    pedidas, respuestas = [], []

    def abrir(url, **_):
        pedidas.append(url)
        relleno = "x" * (tasas.MAX_BYTES_RESPUESTA + 100_000)
        r = _Resp(cuerpo=json.dumps({"rates": {"2026-10-01": {"USD": 0.10}}, "relleno": relleno}).encode())
        respuestas.append(r)
        return r

    monkeypatch.setattr(tasas.url_conector, "abrir", abrir)

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-01", hoy=date(2026, 10, 8))
    assert len(pedidas) == 1
    assert tasas._guardadas("SEK", "2026-09-20", "2026-10-08") == {}
    assert respuestas[0].cerrada
    assert "respuesta inválida" in caplog.text

    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-01", hoy=date(2026, 10, 8))
    assert len(pedidas) == 1   # no insiste durante el caché negativo


def test_body_not_json_is_ignored(base_temporal, monkeypatch):
    tasas._reiniciar_cache()
    monkeypatch.setattr(tasas.url_conector, "abrir", lambda url, **_: _Resp(cuerpo=b"<html>no es json</html>"))
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-01", hoy=date(2026, 10, 8))
    assert tasas._guardadas("SEK", "2026-09-20", "2026-10-08") == {}


def test_bad_date_is_skipped(base_temporal, monkeypatch):
    """Una clave que no es fecha ('2026-13-45', 'ayer', 20261002x) se salta; las buenas se guardan."""
    tasas._reiniciar_cache()
    monkeypatch.setattr(tasas.url_conector, "abrir", lambda url, **_: _Resp({"rates": {
        "2026-13-45": {"USD": 0.10}, "ayer": {"USD": 0.10}, "2026-02-30": {"USD": 0.10},
        "2026-10-01": {"USD": 0.10}, "2026-10-02": {"USD": 0.11}}}))
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-02", hoy=date(2026, 10, 8))
    assert tasas._guardadas("SEK", "2026-09-01", "2026-10-31") == {"2026-10-01": 0.10, "2026-10-02": 0.11}


def test_jump_over_3x_of_previous_stored_rate_is_skipped(base_temporal, monkeypatch, caplog):
    """Con una tasa guardada anterior, una nueva que se aleja más de 3 veces se descarta con un aviso; la siguiente
    se compara con la última que sí se guardó."""
    tasas._reiniciar_cache()
    _sembrar("SEK", {"2026-10-01": 0.10})
    monkeypatch.setattr(tasas.url_conector, "abrir", lambda url, **_: _Resp({"rates": {
        "2026-10-02": {"USD": 0.11},     # normal
        "2026-10-05": {"USD": 0.50},     # x4,5 sobre 0,11: descartada
        "2026-10-06": {"USD": 0.12}}}))  # normal respecto de 0,11
    tasas.asegurar(["SEK"], "2026-10-02", "2026-10-06", hoy=date(2026, 10, 8))
    assert tasas._guardadas("SEK", "2026-09-01", "2026-10-31") == {"2026-10-01": 0.10, "2026-10-02": 0.11,
                                                                   "2026-10-06": 0.12}
    assert "no se guarda" in caplog.text


def test_drop_under_a_third_of_previous_stored_rate_is_skipped(base_temporal, monkeypatch):
    tasas._reiniciar_cache()
    _sembrar("SEK", {"2026-10-01": 0.10})
    monkeypatch.setattr(tasas.url_conector, "abrir", lambda url, **_: _Resp({"rates": {
        "2026-10-02": {"USD": 0.02}, "2026-10-05": {"USD": 0.09}}}))
    tasas.asegurar(["SEK"], "2026-10-02", "2026-10-05", hoy=date(2026, 10, 8))
    assert tasas._guardadas("SEK", "2026-09-01", "2026-10-31") == {"2026-10-01": 0.10, "2026-10-05": 0.09}


def test_jump_without_stored_rate_compares_to_median_of_the_batch(base_temporal, monkeypatch):
    """Sin nada guardado, un valor suelto fuera de 3 veces la mediana de lo que llegó se descarta."""
    tasas._reiniciar_cache()
    monkeypatch.setattr(tasas.url_conector, "abrir", lambda url, **_: _Resp({"rates": {
        "2026-10-01": {"USD": 0.10}, "2026-10-02": {"USD": 0.11}, "2026-10-05": {"USD": 5.0}}}))
    tasas.asegurar(["SEK"], "2026-10-01", "2026-10-05", hoy=date(2026, 10, 8))
    assert tasas._guardadas("SEK", "2026-09-01", "2026-10-31") == {"2026-10-01": 0.10, "2026-10-02": 0.11}
