from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ValidationDecision:
    accepted: bool = True
    needs_manual_review: bool = False
    reasons: tuple[str, ...] = ()
    allow_ai: bool = True

    def as_dict(self):
        return {'accepted': self.accepted, 'needs_manual_review': self.needs_manual_review,
                'reasons': list(self.reasons), 'allow_ai': self.allow_ai}


def today_in_morocco():
    return datetime.now(ZoneInfo('Africa/Casablanca')).date()


def review_unless(condition, reason):
    return ValidationDecision(needs_manual_review=not condition, reasons=() if condition else (reason,))
