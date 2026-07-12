"""Helpers for naming and saving experiment result files.

Result CSVs always carry a timestamp and, when available, a participant id:

- ``{name}_{participant}_{timestamp}.csv`` when a participant id is given.
- ``{name}_{NNN}_{timestamp}.csv`` (iterating fallback number, 4 digits)
  otherwise.

The consent questionnaire builds an anonymous id from its ``pid_1..pid_4``
answers via :func:`participant_id_from_consent`. When several experiment blocks
live in one notebook, keep that id in a ``participant_id`` variable and pass it to
each :func:`save_results` call so all of a participant's files share it. There is
deliberately no cross-notebook state file — the id is just an in-memory value.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

# Question ids the consent questionnaire uses to build the anonymous id.
_DEFAULT_PID_FIELDS = ("pid_1", "pid_2", "pid_3", "pid_4")


def _sanitize(text: object) -> str:
    """Make a string safe to embed in a file name."""
    cleaned = re.sub(r"[^0-9A-Za-z._-]+", "_", str(text).strip())
    return cleaned.strip("_") or "unknown"


def participant_id_from_consent(
    results: pd.DataFrame,
    fields: Sequence[str] = _DEFAULT_PID_FIELDS,
    separator: str = "",
) -> Optional[str]:
    """Build the participant id from a consent questionnaire's results.

    Concatenates the answers of the ``fields`` questions (default
    ``pid_1..pid_4``) in order. Returns ``None`` if the results do not contain
    all of those questions (e.g. a different questionnaire was run, or a field is
    blank), so it is safe to call on any questionnaire result.
    """
    if not isinstance(results, pd.DataFrame) or "question" not in results.columns:
        return None
    answers_by_question = dict(zip(results["question"], results["answer"]))
    parts = []
    for field in fields:
        value = answers_by_question.get(field)
        if value is None or str(value).strip() == "":
            return None
        parts.append(str(value).strip())
    return separator.join(parts)


def _next_number(results_dir: Path, name: str) -> str:
    """Smallest free index for the ``{name}_{NNN}_...`` fallback, as 4 digits.

    Zero-padded to a maximum of 4 digits (``0001``..``9999``); going past 9999
    raises (a participant id should be used long before that). Matches both
    ``{name}_{NNN}.csv`` and ``{name}_{NNN}_{timestamp}.csv`` (the leading
    numeric group is the index). The index group is capped at 4 digits so
    legacy timestamp-only files like ``{name}_20260622_173240.csv`` are not
    mistaken for an index; participant-id files like ``{name}_HPo1_...`` are
    ignored because that group is not all digits.
    """
    pattern = re.compile(rf"^{re.escape(name)}_(\d{{1,4}})(?:_\d+)*\.csv$")
    used = [int(m.group(1)) for f in results_dir.glob(f"{name}_*.csv")
            if (m := pattern.match(f.name))]
    nxt = (max(used) + 1) if used else 1
    # Zero-padded to 4 digits, capped at 4 digits (0001..9999).
    if nxt > 9999:
        raise ValueError(
            f"fallback index for '{name}' exceeded 4 digits (>9999); "
            "use a participant id or clear old result files")
    return f"{nxt:04d}"


def _unique_path(results_dir: Path, stem: str) -> Path:
    """A ``{stem}.csv`` path that does not exist yet (append _2, _3, ...)."""
    path = results_dir / f"{stem}.csv"
    counter = 2
    while path.exists():
        path = results_dir / f"{stem}_{counter}.csv"
        counter += 1
    return path


def save_results(
    results: pd.DataFrame,
    name: str,
    results_dir: str = "results",
    participant_id: Optional[str] = None,
) -> Path:
    """Save a results table to a CSV and return its path.

    The file name always carries a ``{timestamp}``:

    - With a ``participant_id``: ``{name}_{participant}_{timestamp}.csv``.
    - Without one: an iterating fallback number, ``{name}_{NNN}_{timestamp}.csv``
      (``0001``, ``0002``, ...; 4 digits).

    Existing files are never overwritten (a numeric suffix is appended).
    """
    folder = Path(results_dir)
    folder.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if participant_id:
        stem = f"{name}_{_sanitize(participant_id)}_{timestamp}"
    else:
        stem = f"{name}_{_next_number(folder, name)}_{timestamp}"

    path = _unique_path(folder, stem)
    results.to_csv(path, index=False)
    return path


