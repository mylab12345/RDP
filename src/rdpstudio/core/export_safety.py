"""Escaping helpers for user-facing exports.

Exports contain text that came from *remote* machines (command output, host
names) or from imported session files.  A spreadsheet treats a cell starting
with ``=``, ``+``, ``-`` or ``@`` as a formula, so writing that text straight
into a CSV lets a compromised host run formulas on the analyst's machine
(CWE-1236, "CSV injection").  Markdown tables have the same problem with ``|``
and newlines.
"""

from __future__ import annotations

#: Leading characters that make spreadsheet software treat a cell as a formula.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: object) -> str:
    """Return ``value`` as text that cannot start a spreadsheet formula.

    A leading apostrophe is the standard, least-destructive mitigation: the
    cell stays text in Excel/LibreOffice/Sheets and the visible value keeps
    its leading character.
    """
    text = "" if value is None else str(value)
    if not text:
        return text
    # Strip leading whitespace for the check only: Excel ignores it when
    # deciding whether a cell is a formula.
    probe = text.lstrip()
    if probe.startswith(_FORMULA_PREFIXES):
        return "'" + text
    return text


def sanitize_markdown_cell(value: object) -> str:
    """Return ``value`` usable inside a Markdown table cell."""
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


__all__ = ["sanitize_csv_cell", "sanitize_markdown_cell"]
