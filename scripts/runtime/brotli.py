"""Offline decoder-only Brotli API used by FontTools' WOFF2 reader.

The sibling executable is compiled from Google's Brotli for Android ARM64.
WOFF2 encoding is intentionally not supplied: imported fonts are saved as SFNT.
"""
from pathlib import Path
import subprocess

__version__ = "1.2.0-luoshu-decoder"
MAX_INPUT = 128 * 1024 * 1024
MAX_OUTPUT = 256 * 1024 * 1024
_DECODER = Path(__file__).resolve().parents[3] / "bin" / "luoshu-brotli"


class error(Exception):
    """Brotli input was invalid or exceeded the local decoding limits."""


def decompress(data):
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("Brotli input must be bytes-like")
    if len(data) > MAX_INPUT:
        raise error("WOFF2 compressed stream exceeds 128 MiB")
    try:
        result = subprocess.run(
            [str(_DECODER)], input=data, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=90, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise error("WOFF2 Brotli decoder unavailable or timed out") from exc
    if result.returncode or len(result.stdout) > MAX_OUTPUT:
        raise error("WOFF2 contains an invalid, truncated, or oversized Brotli stream")
    return result.stdout
