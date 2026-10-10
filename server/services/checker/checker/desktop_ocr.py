"""Windows desktop OCR without native Unicode filename conversions."""

import io
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from typing import Iterator

from PIL import Image
from pytesseract import pytesseract

_launch_lock = threading.Lock()


def _windows_library():
    import ctypes
    from ctypes import wintypes

    library = ctypes.WinDLL("kernel32", use_last_error=True)
    library.GetDllDirectoryW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
    library.GetDllDirectoryW.restype = wintypes.DWORD
    library.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
    library.SetDllDirectoryW.restype = wintypes.BOOL
    return library


@contextmanager
def clean_dll_directory() -> Iterator[None]:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        yield
        return
    import ctypes

    library = _windows_library()
    size = library.GetDllDirectoryW(0, None)
    previous = ctypes.create_unicode_buffer(size + 1)
    if size:
        library.GetDllDirectoryW(len(previous), previous)
    if not library.SetDllDirectoryW(None):
        raise ctypes.WinError()
    try:
        yield
    finally:
        if not library.SetDllDirectoryW(previous.value or None):
            raise ctypes.WinError()


def image_to_text(image: Image.Image, data_directory: str) -> str:
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    environment = os.environ.copy()
    # Model names, input and output passed to the narrow native CLI are ASCII.
    # CreateProcessW accepts both the executable and cwd as Unicode strings.
    environment["TESSDATA_PREFIX"] = "."
    command = [pytesseract.tesseract_cmd, "stdin", "stdout", "-l", "chi_sim+eng",
               "--psm", "3", "--tessdata-dir", "."]
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        # PyInstaller's DLL search directory is process-wide. Restore it as
        # soon as the child is created, before waiting for OCR to finish.
        with _launch_lock, clean_dll_directory():
            process = subprocess.Popen(
                command, cwd=data_directory, env=environment,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
    except FileNotFoundError as exc:
        raise pytesseract.TesseractNotFoundError() from exc
    with process:
        output, errors = process.communicate(input=encoded.getvalue())
    if process.returncode:
        raise pytesseract.TesseractError(process.returncode, errors.decode("utf-8", errors="replace"))
    return output.decode("utf-8", errors="replace")
