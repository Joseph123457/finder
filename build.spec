# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for JeAn Finder.
#
# Usage:
#   pyinstaller build.spec
#
# Notes:
#  - PyMuPDF / PySide6 는 hiddenimports가 거의 필요 없지만, 일부 서브모듈을
#    자동으로 못 잡는 경우를 대비해 명시한다.
#  - Tesseract 바이너리는 `resources/tesseract/`에 사용자가 미리 넣어두고
#    빌드 시 통째로 datas에 포함시킨다. 파일이 없으면 경고만 찍고 OCR 없이
#    빌드된다 (런타임에 OCR 체크박스가 비활성화됨).

from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

APP_NAME = "JeAnFinder"
ENTRY = Path("src") / "jean_finder" / "__main__.py"
ROOT = Path(".").resolve()

datas = []

# Tesseract 번들 (선택). 존재할 때만 포함.
tess_dir = ROOT / "resources" / "tesseract"
if tess_dir.exists():
    for p in tess_dir.rglob("*"):
        if p.is_file():
            rel = p.parent.relative_to(ROOT)
            datas.append((str(p), str(rel)))
else:
    print("[build.spec] WARNING: resources/tesseract not found - OCR disabled in build")

# PyMuPDF 리소스 (있으면)
try:
    datas += collect_data_files("fitz")
except Exception:
    pass

hiddenimports = []
hiddenimports += collect_submodules("jean_finder")
hiddenimports += [
    "openpyxl",
    "docx",
    "pptx",
    "xlrd",
    "olefile",
    "pytesseract",
    "PIL",
]


a = Analysis(
    [str(ENTRY)],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ROOT / "resources" / "icon.ico") if (ROOT / "resources" / "icon.ico").exists() else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)
