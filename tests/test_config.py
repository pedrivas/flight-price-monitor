from __future__ import annotations

from datetime import date

from monitor.config import load_routes_from_yaml

SAMPLE = """
currency: BRL
routes:
  - name: "Ida e volta"
    origin: gru
    dest: rec
    depart_range: ["2026-11-05", "2026-11-20"]
    return_after_days: [5, 9]
    adults: 2
    target_price: 900
    drop_pct: 20
  - name: "Só ida"
    origin: GRU
    dest: LIS
    depart_range: ["2027-02-01", "2027-02-15"]
    target_price: 3000
"""


def _write(tmp_path, text):
    p = tmp_path / "routes.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_parses_routes(tmp_path):
    routes = load_routes_from_yaml(_write(tmp_path, SAMPLE))
    assert len(routes) == 2

    rt, ow = routes
    assert rt.origin == "GRU" and rt.dest == "REC"       # normalizado p/ maiúsculas
    assert rt.depart_range == (date(2026, 11, 5), date(2026, 11, 20))
    assert rt.return_after_days == (5, 9)
    assert rt.adults == 2
    assert rt.currency == "BRL"

    assert ow.return_after_days is None                   # só ida
    assert ow.adults == 1                                 # default


def test_warns_when_route_has_no_alert_criteria(tmp_path, capsys):
    text = SAMPLE + """  - name: "Sem critério"
    origin: GRU
    dest: GIG
    depart_range: ["2027-03-01", "2027-03-10"]
"""
    load_routes_from_yaml(_write(tmp_path, text))
    err = capsys.readouterr().err
    assert "Sem critério" in err and "alerta" in err
