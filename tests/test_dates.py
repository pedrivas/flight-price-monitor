from datetime import date

from monitor.dates import sample_dates


def test_includes_both_endpoints():
    out = sample_dates(date(2026, 11, 5), date(2026, 11, 20), max_samples=4)
    assert out[0] == date(2026, 11, 5)
    assert out[-1] == date(2026, 11, 20)


def test_respects_max_samples():
    out = sample_dates(date(2026, 1, 1), date(2026, 12, 31), max_samples=4)
    assert len(out) == 4


def test_sorted_and_unique():
    out = sample_dates(date(2026, 1, 1), date(2026, 12, 31), max_samples=5)
    assert out == sorted(out)
    assert len(out) == len(set(out))


def test_short_window_collapses_without_duplicates():
    out = sample_dates(date(2026, 1, 1), date(2026, 1, 2), max_samples=4)
    assert out == [date(2026, 1, 1), date(2026, 1, 2)]


def test_single_day_window():
    d = date(2026, 5, 1)
    assert sample_dates(d, d) == [d]


def test_reversed_range_is_safe():
    assert sample_dates(date(2026, 5, 10), date(2026, 5, 1)) == [date(2026, 5, 10)]


# --- volta até (return_by) ---------------------------------------------------
def _rq(**kw):
    from monitor.models import RouteQuery

    base = dict(name="r", origin="SAO", dest="ATH", depart_range=(date(2027, 5, 26), date(2027, 5, 31)),
                return_after_days=(14, 19))
    base.update(kw)
    return RouteQuery(**base)


def test_trip_without_return_by_uses_midpoint():
    from monitor.dates import trip_for

    assert trip_for(_rq(), date(2027, 5, 26)) == (date(2027, 5, 26), date(2027, 6, 11))  # 16 noites


def test_trip_with_return_by_takes_longest_that_fits():
    from monitor.dates import trip_for

    r = _rq(return_by=date(2027, 6, 14))
    assert trip_for(r, date(2027, 5, 26)) == (date(2027, 5, 26), date(2027, 6, 14))  # 19 noites (máximo)
    assert trip_for(r, date(2027, 5, 31)) == (date(2027, 5, 31), date(2027, 6, 14))  # encurta pra 14
    assert trip_for(r, date(2027, 6, 1)) is None  # nem 14 noites cabem


def test_trip_with_return_by_respects_max_nights():
    from monitor.dates import trip_for

    r = _rq(return_by=date(2027, 7, 30))  # folga de sobra: limite é a faixa de noites
    assert trip_for(r, date(2027, 5, 26)) == (date(2027, 5, 26), date(2027, 6, 14))


def test_sample_trips_never_passes_return_by():
    from monitor.dates import sample_trips

    r = _rq(depart_range=(date(2027, 5, 20), date(2027, 6, 10)), return_by=date(2027, 6, 14))
    trips = sample_trips(r)
    assert trips and all(ret <= date(2027, 6, 14) and (ret - dep).days >= 14 for dep, ret in trips)
    assert trips[-1][0] == date(2027, 5, 31)  # janela de ida cortada na última ida que cabe


def test_sample_trips_empty_when_nothing_fits():
    from monitor.dates import sample_trips

    assert sample_trips(_rq(return_by=date(2027, 6, 1))) == []


def test_one_way_ignores_return_by():
    from monitor.dates import trip_for

    assert trip_for(_rq(return_after_days=None, return_by=date(2027, 6, 1)), date(2027, 5, 26)) == (date(2027, 5, 26), None)
