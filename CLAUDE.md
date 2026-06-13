## Build system

This project uses pyproject.toml as the single source of truth for
dependencies. Nuitka build flags live in main_qt.py as # nuitka-project:
comments — the native Nuitka mechanism for per-project configuration.

### Running locally
  pip install -e ".[dev]"      # install all deps including dev tools
  build_nuitka.bat             # compiles the app

### Nuitka flags
All static flags live in main_qt.py as `# nuitka-project: --flag` comments.
Nuitka 4.1.2 reads these automatically when compiling main_qt.py.
Only dynamic flags (--jobs, --file-version, --product-version, --report)
stay in build_nuitka.bat.

Do NOT move flags back into build_nuitka.bat.
Do NOT add a [tool.nuitka] section in pyproject.toml — Nuitka 4.1.2 does
not read it when called directly via `python -m nuitka`.

### Version
Single source: APP_VERSION in build_nuitka.bat (format X.Y.Z.W).
For MSIX builds: pass as parameter → .\build-msix.ps1 -Version "1.3.0.0"

### Do NOT generate
- New .bat build scripts
- Inline nuitka flag lists in any script or workflow
- requirements.txt (use pyproject.toml dependencies instead)
