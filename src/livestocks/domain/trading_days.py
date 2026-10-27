"""Trading-day arithmetic on unix timestamps, skipping Saturday and Sunday.
Used to derive the Cum Date and the Recording Date from an Ex Date when the feed has no value.
Market holidays are not known here, so a derived date can be one or two days off around a holiday.
"""

from datetime import UTC, datetime, timedelta


def shift_trading_days(ts: int, days: int) -> int:
    """Move a unix timestamp by whole trading days, keeping its time of day.
    Weekends are skipped by the UTC weekday, the zone the feed stamps its dates in.
    Zero days returns the timestamp unchanged.
    """
    step = 1 if days >= 0 else -1
    moment = datetime.fromtimestamp(ts, UTC)
    remaining = abs(days)
    while remaining:
        moment += timedelta(days=step)
        if moment.weekday() < 5:
            remaining -= 1
    return int(moment.timestamp())
