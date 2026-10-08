"""Mapping from TradingView's 1-5 consensus score to a rating label."""

from livestocks.domain.models import RatingTone


def rating_label(mark: float | None) -> tuple[str, RatingTone]:
    """Return the label and tone for a consensus score (1 = strong buy, 5 = strong sell)."""
    if mark is None:
        return "No rating", RatingTone.NONE
    if mark < 1.5:
        return "Strong buy", RatingTone.BUY
    if mark < 2.5:
        return "Buy", RatingTone.BUY
    if mark < 3.5:
        return "Neutral", RatingTone.HOLD
    if mark < 4.5:
        return "Sell", RatingTone.SELL
    return "Strong sell", RatingTone.SELL
