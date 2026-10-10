import io
from types import SimpleNamespace

import pytest
from PIL import Image
from pytesseract import pytesseract

from checker import desktop_ocr, extract_pdf


@pytest.mark.parametrize("exit_code", [0, 1])
def test_ocr_passes_png_via_stdin_and_preserves_native_result(tmp_path, monkeypatch, exit_code) -> None:
    models = tmp_path / "中文 用户" / "语言包"
    models.mkdir(parents=True)
    executable = str(tmp_path / "中文 应用" / "tesseract.exe")
    monkeypatch.setattr(pytesseract, "tesseract_cmd", executable)
    monkeypatch.setenv("TESSDATA_PREFIX", str(models))
    result = "标书质量检查\n".encode("utf-8")
    error = b"Error opening data file ./eng.traineddata\n"
    launched = []

    class OCRProcess:
        returncode = exit_code

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def communicate(self, *, input):
            with Image.open(io.BytesIO(input)) as image:
                assert image.format == "PNG" and image.size == (80, 30)
            return result, error

    def launch(command, **options):
        assert command[0] == executable
        assert command[1:3] == ["stdin", "stdout"]
        assert command[command.index("--tessdata-dir") + 1] == "."
        assert options["cwd"] == str(models)
        assert options["env"]["TESSDATA_PREFIX"] == "."
        assert options.get("shell", False) is False
        launched.append(True)
        return OCRProcess()

    monkeypatch.setattr(desktop_ocr.subprocess, "Popen", launch)
    if exit_code:
        with pytest.raises(pytesseract.TesseractError) as failure:
            desktop_ocr.image_to_text(Image.new("RGB", (80, 30), "white"), str(models))
        assert failure.value.status == exit_code
        assert "./eng.traineddata" in failure.value.message
    else:
        assert desktop_ocr.image_to_text(Image.new("RGB", (80, 30), "white"), str(models)) == result.decode("utf-8")
    assert launched


def test_frozen_windows_ocr_restores_dll_directory_when_launch_fails(tmp_path, monkeypatch) -> None:
    original_directory = str(tmp_path / "backend" / "_internal")

    class Kernel:
        directory = original_directory

        def GetDllDirectoryW(self, size, target):
            if target is not None:
                target.value = self.directory
            return len(self.directory) + (1 if not size else 0)

        def SetDllDirectoryW(self, directory):
            self.directory = directory
            return True

    kernel = Kernel()
    monkeypatch.setattr(desktop_ocr.sys, "platform", "win32")
    monkeypatch.setattr(desktop_ocr.sys, "frozen", True, raising=False)
    monkeypatch.setattr(desktop_ocr.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(desktop_ocr, "_windows_library", lambda: kernel)

    def failed_launch(*_args, **_kwargs):
        assert kernel.directory is None
        raise FileNotFoundError("missing OCR executable")

    monkeypatch.setattr(desktop_ocr.subprocess, "Popen", failed_launch)
    with pytest.raises(pytesseract.TesseractNotFoundError):
        desktop_ocr.image_to_text(Image.new("RGB", (80, 30), "white"), str(tmp_path))
    assert kernel.directory == original_directory


@pytest.mark.parametrize("platform, data_directory, expected", [
    ("win32", "中文语言包目录", "desktop"),
    ("win32", None, "server"),
    ("darwin", "中文语言包目录", "server"),
])
def test_pdf_ocr_uses_desktop_path_only_when_explicitly_configured(monkeypatch, platform, data_directory, expected):
    image = Image.new("RGB", (80, 30), "white")
    page = SimpleNamespace(width=595, height=842, to_image=lambda **_kwargs: SimpleNamespace(original=image))
    monkeypatch.setattr(extract_pdf.sys, "platform", platform)
    if data_directory:
        monkeypatch.setenv("CHECKER_TESSERACT_CWD", data_directory)
    else:
        monkeypatch.delenv("CHECKER_TESSERACT_CWD", raising=False)
    monkeypatch.setattr(desktop_ocr, "image_to_text", lambda *_args: "desktop")
    monkeypatch.setattr(extract_pdf.pytesseract, "image_to_string", lambda *_args, **_kwargs: "server")
    assert extract_pdf._ocr_text(page, 1) == expected


def test_pdf_ocr_logs_engine_stderr_and_path_context(monkeypatch, caplog) -> None:
    image = Image.new("RGB", (80, 30), "white")
    page = SimpleNamespace(width=595, height=842, to_image=lambda **_kwargs: SimpleNamespace(original=image))
    monkeypatch.setattr(extract_pdf.sys, "platform", "win32")
    monkeypatch.setenv("CHECKER_TESSERACT_CWD", "中文语言包目录")

    def failed_ocr(*_args):
        raise pytesseract.TesseractError(1, "Could not load ./chi_sim.traineddata")

    monkeypatch.setattr(desktop_ocr, "image_to_text", failed_ocr)
    with pytest.raises(ValueError, match="OCR 不可用"):
        extract_pdf._ocr_text(page, 5)
    assert "page=5" in caplog.text
    assert "Could not load ./chi_sim.traineddata" in caplog.text
    assert "中文语言包目录" in caplog.text
