"""Common bounded input for offline client capture inspection tools."""

import argparse
from pathlib import Path

MAX_INPUT_BYTES = 1024 * 1024


def exit_code(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Expected a signed 64-bit integer.") from None
    if not -(2**63) <= number <= 2**63 - 1:
        raise argparse.ArgumentTypeError("Expected a signed 64-bit integer.")
    return number


def read_capture(path: Path) -> bytes:
    if not path.is_file():
        raise OSError("Capture is not a file.")
    with path.open("rb") as source:
        return source.read(MAX_INPUT_BYTES + 1)
