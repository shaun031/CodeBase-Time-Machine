from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalScores:
    volatility: float
    stability: float
    classification: str


VOLATILITY_FORMULA = (
    "0.35*min(changes_in_configured_recent_window/6,1) + 0.30*min(total_changes/12,1) + "
    "0.20*min(major_rewrites/3,1) + 0.15*min(contributors/5,1)"
)
STABILITY_FORMULA = (
    "0.50*(days_since_change/(days_since_change+180)) + "
    "0.30*(1/(1+total_changes/4)) + "
    "0.20*(1-min(changes_in_configured_recent_window/6,1))"
)


def temporal_scores(
    *,
    age_days: int,
    days_since_change: int,
    changes_180d: int,
    total_changes: int,
    rewrites: int,
    contributors: int,
    deleted: bool,
) -> TemporalScores:
    recent = min(max(changes_180d, 0) / 6, 1)
    total = min(max(total_changes, 0) / 12, 1)
    rewrite = min(max(rewrites, 0) / 3, 1)
    people = min(max(contributors, 0) / 5, 1)
    volatility = round(0.35 * recent + 0.30 * total + 0.20 * rewrite + 0.15 * people, 4)
    elapsed = max(days_since_change, 0)
    stability = round(
        0.50 * (elapsed / (elapsed + 180))
        + 0.30 * (1 / (1 + max(total_changes, 0) / 4))
        + 0.20 * (1 - recent),
        4,
    )
    if deleted:
        label = "deleted"
    elif rewrites and changes_180d:
        label = "recently_rewritten"
    elif age_days >= 365 and changes_180d == 0 and total_changes <= 2:
        label = "stable_legacy"
    elif age_days < 90:
        label = "new_code"
    elif volatility >= 0.65:
        label = "frequently_changed"
    elif age_days >= 365 and changes_180d:
        label = "long_lived_active"
    elif changes_180d == 0:
        label = "recently_inactive"
    else:
        label = "active"
    return TemporalScores(volatility, stability, label)
