from livestocks.models import rating_label
from livestocks.ui.components import duration, kpi_strip, price_fmt, range_bar, rate_pill


def test_price_fmt():
    assert price_fmt(2310.0) == "2,310"
    assert price_fmt(3394.09) == "3,394"
    assert price_fmt(333.63) == "333.63"
    assert price_fmt(None) == "—"


def test_duration():
    assert duration(0) == "now" and duration(30) == "<1m" and duration(3 * 3600 + 5 * 60) == "3h 05m"


def test_rating_label_bounds():
    assert rating_label(1.0) == ("Strong buy", "buy")
    assert rating_label(2.0) == ("Buy", "buy")
    assert rating_label(3.0) == ("Neutral", "hold")
    assert rating_label(5.0) == ("Strong sell", "sell")
    assert rating_label(None)[1] == "none"
    assert "—" in rate_pill(None)


def test_kpi_strip_empty_rows_does_not_crash():
    assert "Tracked tickers" in kpi_strip([])


def test_dist_card_separates_sell_and_strong_sell():
    from livestocks.models import Forecast, TickerRow
    from livestocks.ui.components import dist_card

    def row(sym, mark):
        f = Forecast("IDX", sym, None, 1.0, None, 1.0, 1.0, 1.0, 1, mark, 1, None, None)
        return TickerRow("IDX", sym, None, 0, 1, 0, None, 0, False, f, 1)

    html = dist_card([row("A", 1.2), row("B", 3.8), row("C", 4.8)])
    assert "Strong sell" in html and html.count('<div><span><i style="background:') == 5
    assert dist_card([]) == ""
