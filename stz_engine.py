"""
Frozen entry point for the STZ XML Translator engine.

The installed app is the Tauri shell (``stz-xml-translator.exe``); it starts
this headless engine next to itself. Run from source with ``python -m engine``.
"""

# nuitka-project: --standalone
# nuitka-project: --msvc=latest
# nuitka-project: --windows-console-mode=disable
# nuitka-project: --lto=no
# nuitka-project: --python-flag=no_docstrings
# nuitka-project: --noinclude-pytest-mode=nofollow
# nuitka-project: --noinclude-unittest-mode=nofollow
# nuitka-project: --include-data-dir=locales=locales
# nuitka-project: --include-data-dir=assets=assets
# nuitka-project: --nofollow-import-to=tests
# nuitka-project: --nofollow-import-to=*.tests
# nuitka-project: --nofollow-import-to=ruff
# nuitka-project: --nofollow-import-to=pygments
# nuitka-project: --nofollow-import-to=PySide6
# nuitka-project: --nofollow-import-to=mcp
# nuitka-project: --assume-yes-for-downloads
# nuitka-project: --output-filename=stz-xml-engine.exe
# nuitka-project: --output-dir=dist
# nuitka-project: --windows-icon-from-ico=assets/icon.ico
# nuitka-project: --company-name=STZ Labs
# nuitka-project: --product-name=STZ XML Translator
# nuitka-project: --file-description=STZ XML Translator engine
import sys

from engine.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
