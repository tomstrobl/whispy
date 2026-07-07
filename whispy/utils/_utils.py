import re

def format_markdown(text: str) -> str:
    """
    Format markdown strings to work as intended

    Forces correct markdown syntax as a convenience.

    1. ``'&nbsp;'`` is inserted between a sequence of two linebreaks ``'\n\n'``
       to force rendering of two line breaks (spaces between linebreaks
       allowed).
    2. Two blank spaces ``'  '`` are inserted before each line break to force
       the line break.

    Parameters
    ----------
    text : str
        markdown string

    Returns
    -------
    str
        markdown string with extended formatting
    """
    normalized = re.sub(r"\n[ ]*\n", "\n&nbsp;\n", text)

    lines = normalized.split("\n")
    out: list[str] = []

    for idx, line in enumerate(lines):
        out.append(line)
        if idx == len(lines) - 1:
            continue

        next_line = lines[idx + 1]
        # In Qt markdown, a hard line break inside a list item can make the
        # following plain line render as a new bullet. End the list first.
        if (
            re.match(r"^\s*([-+*]|\d+[.)])\s+", line)
            and not re.match(r"^\s*([-+*]|\d+[.)])\s+", next_line)
            and next_line.strip()
        ):
            out.append("\n\n")
        else:
            out.append("  \n")

    return "".join(out)