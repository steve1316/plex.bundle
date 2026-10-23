# coding=utf-8

import re


# Pattern for standard JAV video codes (e.g. "JBD-226"), with an optional numeric amateur prefix (e.g. "230OREMO-042")
# and ignored "-4k" / "-ub" / "-uc" / "-unblurred" / "-uncensored" suffixes (e.g. "SCOH-182-4k", "ABC-123-4k-uc")
VIDEO_CODE_PATTERN = re.compile(
    r"(?:^|\s|\[|\(|\.|\\|/)"
    r"(\d*[a-zA-Z]+-[a-zA-Z]*\d+)"
    r"(?:[-_](?:4k|ub|uc|unblurred|uncensored))*"
    r"(?:$|\s|\]|\)|\.)",
    re.IGNORECASE,
)


def guess_video_code(text):
    """Try to extract a JAV video code (e.g. ``ABC-123``) from *text*.

    Args:
        text (str): Arbitrary string such as a filename or directory name.

    Returns:
        str or None: The upper-cased video code, or ``None``.
    """
    match = VIDEO_CODE_PATTERN.search(text)
    if match:
        return match.group(1).upper()
    return None


def br_to_newlines(text):
    """Convert HTML `<br>` tags in `text` to newlines and trim the spaces around each line break.

    Args:
        text (str): Text that may contain `<br>`, `<br/>` or `<br />` tags.

    Returns:
        str: The text with line breaks, or the input unchanged when it is empty.
    """
    if not text:
        return text
    text = re.sub(r"(?i)<br\s*/?>", u"\n", text)
    return re.sub(r"[ \t]*\n[ \t]*", u"\n", text).strip()


def get_code_group(video_code):
    """Extract the code group from a video code, e.g. "ABC" from "ABC-123".

    Args:
        video_code (str): A JAV video code.

    Returns:
        str or None: The code group, or ``None`` if the input is not a valid video code.
    """
    if not video_code:
        return None
    parts = video_code.split("-", 1)
    if len(parts) == 2:
        return parts[0].upper()
    return None
