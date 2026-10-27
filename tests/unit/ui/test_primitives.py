from livestocks.ui.primitives import card, crumb, empty_card, page_title, th, trunc


class TestCard:
    def test_escapes_title_and_subtitle(self):
        html = card("<b>T</b>", "<p>body</p>", sub="<i>s</i>")

        assert "&lt;b&gt;T&lt;/b&gt;" in html
        assert "&lt;i&gt;s&lt;/i&gt;" in html

    def test_labelled_card_exposes_its_name(self):
        assert 'aria-label="Forecast"' in card("Forecast", "", label="Forecast")

    def test_padded_card_wraps_the_body(self):
        assert '<div class="card-body">x</div>' in card("T", "x")

    def test_unpadded_card_leaves_the_body_flush(self):
        html = card("T", "x", padded=False)

        assert 'class="card-body"' not in html
        assert "x</section>" in html


class TestCrumb:
    def test_last_part_is_the_current_page(self):
        html = crumb(("Dashboard", "/"), ("Calendar", None))

        assert '<a href="/">Dashboard</a>' in html
        assert '<span aria-current="page">Calendar</span>' in html

    def test_trail_is_a_labelled_navigation(self):
        assert 'aria-label="Breadcrumb"' in crumb(("Home", None))

    def test_separators_are_hidden_from_assistive_technology(self):
        assert '<span aria-hidden="true">/</span>' in crumb(("A", "/"), ("B", None))

    def test_labels_are_escaped(self):
        assert "&lt;x&gt;" in crumb(("<x>", None))


class TestPageTitle:
    def test_renders_one_heading_with_subtitle(self):
        html = page_title("Calendar", "IDX")

        assert html.count("<h1>") == 1
        assert '<span class="sub">IDX</span>' in html

    def test_subtitle_is_optional(self):
        assert 'class="sub"' not in page_title("Calendar")


class TestEmptyCard:
    def test_explains_why_the_area_is_empty(self):
        html = empty_card("No data", "Nothing yet.")

        assert "<h3>No data</h3>" in html
        assert "<p>Nothing yet.</p>" in html

    def test_action_is_placed_after_the_text(self):
        html = empty_card("T", "x", action='<button class="btn">Go</button>')

        assert html.index("<p>x</p>") < html.index("Go</button>")

    def test_text_is_escaped(self):
        assert "&lt;script&gt;" in empty_card("<script>", "x")


class TestTableHeader:
    def test_defaults_to_column_scope(self):
        assert th("Ticker") == '<th scope="col">Ticker</th>'

    def test_row_header_and_classes(self):
        assert th("SIDO", scope="row", classes="r") == '<th scope="row" class="r">SIDO</th>'


class TestTrunc:
    def test_full_text_is_kept_in_the_tooltip(self):
        html = trunc("PT Industri Jamu dan Farmasi Sido Muncul Tbk")

        assert 'title="PT Industri Jamu dan Farmasi Sido Muncul Tbk"' in html
        assert 'class="trunc"' in html

    def test_quotes_cannot_break_out_of_the_attribute(self):
        assert 'title="a&quot;onmouseover=x"' in trunc('a"onmouseover=x')
