from whispy.utils._utils import format_markdown


def test_format_markdown_keeps_hard_line_breaks() -> None:
    text = "Line A\nLine B"
    assert format_markdown(text) == "Line A  \nLine B"


def test_format_markdown_adds_spacer_for_spaces_only_separator_line() -> None:
    text = "Line A\n   \nLine B"
    assert format_markdown(text) == "Line A  \n&nbsp;  \nLine B"


def test_format_markdown_preserves_markdown_content() -> None:
    text = "Line A\n**Bold**\nLine B"
    assert format_markdown(text) == "Line A  \n**Bold**  \nLine B"


def test_format_markdown_keeps_list_item_continuation_plain() -> None:
    text = "- Bullet point\nSome text."
    assert format_markdown(text) == "- Bullet point\n\nSome text."


def test_format_markdown_keeps_regular_list_items() -> None:
    text = "- Item A\n- Item B"
    assert format_markdown(text) == "- Item A  \n- Item B"
