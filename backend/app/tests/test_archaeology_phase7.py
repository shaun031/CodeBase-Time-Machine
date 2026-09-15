from app.services.archaeology.similarity import changed_lines, code_similarity, normalized_tokens
from app.services.archaeology.volatility import temporal_scores


def test_normalized_similarity_ignores_comments_and_formatting() -> None:
    left = """def calculate_tax(total):
    # old explanation
    return total * 0.2
"""
    right = """def calculate_tax(total):
    return total*0.2  # new explanation
"""
    assert normalized_tokens(left) == normalized_tokens(right)
    assert code_similarity(left, right) == 1.0


def test_rewrite_similarity_and_line_counts_are_deterministic() -> None:
    old = "def find_user(user_id):\n    return database.get(user_id)\n"
    new = (
        "def find_user(user_id, include_deleted=False):\n"
        "    query = users.where(id=user_id)\n"
        "    if not include_deleted:\n"
        "        query = query.where(deleted=False)\n"
        "    return query.first()\n"
    )
    added, deleted = changed_lines(old, new)
    assert code_similarity(old, new) < 0.5
    assert added == 5
    assert deleted == 2


def test_volatile_code_scores_above_stable_legacy_code() -> None:
    volatile = temporal_scores(
        age_days=200,
        days_since_change=2,
        changes_180d=9,
        total_changes=18,
        rewrites=2,
        contributors=4,
        deleted=False,
    )
    stable = temporal_scores(
        age_days=1500,
        days_since_change=900,
        changes_180d=0,
        total_changes=1,
        rewrites=0,
        contributors=1,
        deleted=False,
    )
    assert volatile.volatility > stable.volatility
    assert volatile.stability < stable.stability
    assert volatile.classification == "recently_rewritten"
    assert stable.classification == "stable_legacy"


def test_recent_rewrite_and_deleted_classifications_are_explicit() -> None:
    rewritten = temporal_scores(
        age_days=400,
        days_since_change=3,
        changes_180d=1,
        total_changes=5,
        rewrites=1,
        contributors=2,
        deleted=False,
    )
    deleted = temporal_scores(
        age_days=400,
        days_since_change=3,
        changes_180d=1,
        total_changes=5,
        rewrites=1,
        contributors=2,
        deleted=True,
    )
    assert rewritten.classification == "recently_rewritten"
    assert deleted.classification == "deleted"
