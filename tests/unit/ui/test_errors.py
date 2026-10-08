from livestocks.domain import InvalidTickerError
from livestocks.services import CrawlTimeoutError
from livestocks.ui.errors import describe


class TestDescribe:
    def test_domain_errors_are_shown_as_their_own_message(self):
        assert (
            describe(InvalidTickerError("'a b' is not a valid ticker."))
            == "'a b' is not a valid ticker."
        )

    def test_service_errors_are_shown_as_their_own_message(self):
        assert describe(CrawlTimeoutError("not ready")) == "not ready"

    def test_unexpected_errors_never_leak_their_details(self):
        text = describe(RuntimeError("secret path /etc/passwd"))

        assert "secret" not in text
        assert "went wrong" in text
