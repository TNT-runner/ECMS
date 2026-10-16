# Build a single Windows executable; personal inventory stays outside the bundle.
from pathlib import Path

source = Path(SPECPATH).parent
analysis = Analysis(
    [str(source / "app.py")],
    pathex=[str(source)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
archive = PYZ(analysis.pure)
executable = EXE(
    archive,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="元件仓库",
    icon=str(source / "packaging" / "ComponentDesk.ico"),
    console=False,
    debug=False,
    strip=False,
    upx=False,
    disable_windowed_traceback=False,
)
