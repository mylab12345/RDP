"""Pure fuzzy-matching helpers used by interactive search UIs."""

from __future__ import annotations


def fuzzy_score(needle: str, text: str) -> int:
    """Subsequence fuzzy matcher — higher is better, 0 means no match.

    Rewards early hits, consecutive runs and word-boundary matches, so
    ``nw`` ranks "Network Tools" above "New Session".
    """
    needle = needle.lower()
    text = text.lower()
    if not needle:
        return 1
    if len(needle) > len(text):
        return 0
    score = 0
    ti = 0
    prev = -2
    for ch in needle:
        found = text.find(ch, ti)
        if found < 0:
            return 0
        score += max(0, 10 - found // 2)
        if found == prev + 1:
            score += 6
        if found == 0 or text[found - 1] in " \t·/_&-:(":
            score += 5
        prev = found
        ti = found + 1
    return score


__all__ = ["fuzzy_score"]
