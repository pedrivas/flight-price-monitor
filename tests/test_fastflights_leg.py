from __future__ import annotations

from types import SimpleNamespace

from monitor.sources.fastflights import _build_leg


def _seg(from_code, to_code, dep, arr, duration):
    return SimpleNamespace(
        from_airport=SimpleNamespace(code=from_code),
        to_airport=SimpleNamespace(code=to_code),
        departure=SimpleNamespace(date=dep[0], time=dep[1]),
        arrival=SimpleNamespace(date=arr[0], time=arr[1]),
        duration=duration,
    )


def test_build_leg_direct():
    # 10/04 15:30 -> 11/04 06:45 = 15h15 = 915 min; sem conexão o total bate com o segmento
    segs = [_seg("GRU", "IST", ((2027, 4, 10), (15, 30)), ((2027, 4, 11), (6, 45)), 915)]
    leg = _build_leg(segs)
    assert leg.airports == ["GRU", "IST"]
    assert leg.seg_minutes == [915]
    assert leg.layover_minutes == []
    assert leg.total_minutes == 915
    assert leg.stops == 0


def test_build_leg_with_connection_computes_layover_and_total():
    segs = [
        _seg("GRU", "LHR", ((2027, 4, 10), (15, 30)), ((2027, 4, 11), (6, 50)), 680),
        _seg("LHR", "IST", ((2027, 4, 11), (8, 40)), ((2027, 4, 11), (14, 35)), 235),
    ]
    leg = _build_leg(segs)
    assert leg.airports == ["GRU", "LHR", "IST"]
    assert leg.seg_minutes == [680, 235]
    assert leg.layover_minutes == [110]  # 08:40 - 06:50 = 1h50
    assert leg.total_minutes == 23 * 60 + 5  # 10/04 15:30 -> 11/04 14:35
    assert leg.stops == 1


def test_build_leg_empty_returns_none():
    assert _build_leg([]) is None


def test_build_leg_malformed_segment_returns_none():
    assert _build_leg([SimpleNamespace(from_airport=None)]) is None
