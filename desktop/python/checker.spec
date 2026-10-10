"""Freeze the interpreter and backend dependencies into an onedir runtime.

Build from the repository root with:
  uv run --project server/services/checker --group packaging pyinstaller \
    --noconfirm --clean --distpath desktop/python/dist \
    --workpath desktop/python/build desktop/python/checker.spec

OCR executables and language data are collected separately by electron-builder.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files


repository = Path(SPECPATH).resolve().parents[1]
rapidfuzz_data, rapidfuzz_binaries, rapidfuzz_imports = collect_all(
    "rapidfuzz", filter_submodules=lambda name: ".__pyinstaller" not in name
)
datas = rapidfuzz_data
# python-docx accesses templates through parts/../templates; the parts directory
# must physically exist even though its imported modules live in the PYZ.
datas += collect_data_files("docx", include_py_files=True)
for package in ("pdfminer", "pdfplumber", "pypdf"):
    datas += collect_data_files(package)

analysis = Analysis(
    [str(repository / "desktop/python/entrypoint.py")],
    pathex=[str(repository / "server/services/checker")],
    binaries=rapidfuzz_binaries,
    datas=datas,
    hiddenimports=rapidfuzz_imports + [
        "uvicorn.logging",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "reportlab", "pandas", "numpy", "matplotlib", "tkinter"],
    noarchive=False,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="checker-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="checker-backend",
)
