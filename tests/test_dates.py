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
