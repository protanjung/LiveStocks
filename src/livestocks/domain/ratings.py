"""Mapping from TradingView's 1-5 consensus score to a rating label.
The same cut-offs drive the table pills, the gauge and the rating mix.
Tones group the five labels into buy, hold and sell.
"""

from livestocks.domain.models import RatingTone


def rating_label(mark: float | None) -> tuple[str, RatingTone]:
    """Return the label and tone for a score (1 = strong buy, 5 = strong sell).
    Scores below 1.5 are strong buy, then every whole step is one label.
    None gives 'No rating' with the NONE tone.
    """
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
