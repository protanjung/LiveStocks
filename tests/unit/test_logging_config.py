import json
import logging
import sys

import pytest
from loguru import logger

from livestocks.logging_config import configure_logging


@pytest.fixture(autouse=True)
def restore_logging():
    yield
    logger.remove()
    logger.add(sys.stderr)
    logging.basicConfig(handlers=[], force=True)


class TestConfigureLogging:
    def test_text_format_writes_the_message_to_stderr(self, capsys):
        configure_logging("INFO")

        logger.info("hello text")

        assert "hello text" in capsys.readouterr().err

    def test_json_format_writes_one_object_per_line_with_bound_fields(self, capsys):
        configure_logging("INFO", json=True)

        logger.bind(ticker="IDX:TLKM").warning("crawl slow")

        record = json.loads(capsys.readouterr().err.strip().splitlines()[-1])["record"]
        assert record["message"] == "crawl slow"
        assert record["level"]["name"] == "WARNING"
        assert record["extra"] == {"ticker": "IDX:TLKM"}

    def test_records_below_the_level_are_dropped(self, capsys):
        configure_logging("WARNING")

        logger.info("quiet")
        logger.warning("loud")

        err = capsys.readouterr().err
        assert "quiet" not in err
        assert "loud" in err

    def test_standard_library_records_are_forwarded_to_loguru(self, capsys):
        configure_logging("INFO")

        logging.getLogger("some.library").warning("from the stdlib")

        assert "from the stdlib" in capsys.readouterr().err
