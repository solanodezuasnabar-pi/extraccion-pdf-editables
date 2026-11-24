# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — Emisión Plan Familia VAVI.

Build (desde la raíz del repo, con el venv activo):

    .venv\\Scripts\\pip install pyinstaller
    .venv\\Scripts\\pyinstaller main.spec

Salida:

    dist/EmisionPlanFamiliaVAVI/EmisionPlanFamiliaVAVI.exe
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None
ROOT = Path(SPECPATH).resolve()

# PyMuPDF / fitz: binarios y datos nativos
fitz_datas, fitz_binaries, fitz_hidden = collect_all("fitz")
pymupdf_datas, pymupdf_binaries, pymupdf_hidden = collect_all("pymupdf")
msal_datas, msal_binaries, msal_hidden = collect_all("msal")
requests_datas, requests_binaries, requests_hidden = collect_all("requests")

datas = [
    (str(ROOT / "configs"), "configs"),
    (str(ROOT / "config"), "config"),
    (str(ROOT / "templates"), "templates"),
    (str(ROOT / "Plantillas"), "Plantillas"),
    (str(ROOT / "scripts" / "graph_token_windows.ps1"), "scripts"),
]
datas += fitz_datas + pymupdf_datas + msal_datas + requests_datas
datas += collect_data_files("openpyxl")

binaries = fitz_binaries + pymupdf_binaries + msal_binaries + requests_binaries

hiddenimports = sorted(
    set(
        fitz_hidden
        + pymupdf_hidden
        + msal_hidden
        + requests_hidden
        + [
            "fitz",
            "pymupdf",
            "openpyxl",
            "yaml",
            "dotenv",
            "dateutil",
            "dateutil.relativedelta",
            "jinja2",
            "msal",
            "requests",
            "src",
            "src.process_manager",
            "src.paths",
            "src.settings",
            "src.lote",
            "src.completitud",
            "src.labels",
            "src.graph_config",
            "src.graph_http",
            "src.graph_auth",
            "src.graph_conector",
            "src.libs.config_manager",
            "src.libs.log_manager",
            "src.libs.notification_manager",
            "src.extractors.n1_formfields",
            "src.classifier",
            "src.selector",
            "src.normalizer",
            "src.validator",
            "src.excel_builder",
            "src.report_builder",
            "src.validation_builder",
            "src.rules",
            "src.periodo",
            "src.excel_asesor",
        ]
    )
)

a = Analysis(
    ["main.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EmisionPlanFamiliaVAVI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # CLI visible: --mes, --anio, logs en consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="EmisionPlanFamiliaVAVI",
)
