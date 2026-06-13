# STZ XML Translator

A desktop tool for modders and localization teams to translate XML files from games or other structured content. Built with Python 3.12 + PySide6 + QML, it provides a modern interface to load XML files, preview original strings, apply AI or machine translations in batch or individually, review results, and export the updated file — without altering the original structure, attributes, or namespace.

![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![Python](https://img.shields.io/badge/python-3.12-blue)
![Qt](https://img.shields.io/badge/Qt-6.7%2B-green)
![License](https://img.shields.io/badge/license-GPLv3%20%2F%20Commercial-orange)

---

## Features

- **Smart XML parser** — auto-detects repeating elements; extracts only target text fields while preserving attributes, node order, and namespaces.
- **Multiple translation providers** — Google Translate (free, no key), Google Gemini (AI, batch of 120), DeepL, Microsoft Azure Translator, and Ollama (local LLM).
- **Provider-adaptive UI** — AI-specific controls (Context/Theme field, AI model selector) only appear when an AI provider is selected; button labels adapt accordingly.
- **Batch and single translation** — translate all pending entries at once or individually; progress is checkpointed after each batch so you can resume later.
- **Tag picker with presets** — auto-detect parent/child tags from the loaded file; save named presets for quick reuse across sessions.
- **Themes** — five built-in themes: Windows Fluent, Neutral Deep, Cool Tint (dark), Light Azure, and Beige Café (light). All colours are fully tokenized.
- **Multi-language UI** — interface strings in five languages: English, Portuguese (BR), Spanish, French, and Japanese.
- **Glossary manager** — define fixed word pairs that are injected into AI prompts for consistent terminology across the whole game.
- **Save in place** — overwrite the original file and auto-reload; the translated text becomes the new original for follow-up passes.
- **Export / Import** — backup and restore translations via JSON or CSV without touching the XML.

---

## Quick Start

**Requirements:** Python 3.12 · Windows 10/11 (FluentWinUI3 requires Qt 6.7+)

```powershell
git clone https://github.com/StarzynhoBR/STZ-XML-Translator.git
cd STZ-XML-Translator
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python main_qt.py
```

No API key is required to run the app. Google Translate (free) works out of the box; AI providers require a key configured via the **API Key Configuration** button.

---

## Installing a Release Build

Release builds are distributed as a signed MSIX package. Download these three files from the same GitHub Release and keep them in the same folder:

- `STZXMLTranslator-x.y.z.0.msix`
- `STZXMLTranslator.cer`
- `install-app.ps1`

Then run the installer script:

```powershell
powershell -ExecutionPolicy Bypass -File .\install-app.ps1
```

Why a script? The MSIX is signed with the project's certificate, so Windows must trust the public `.cer` certificate before installing the package. The script is intentionally small and readable: it installs `STZXMLTranslator.cer` into the Windows Trusted Root store and then installs the `.msix` with `Add-AppxPackage`.

If you prefer to review it first, open `install-app.ps1` in a text editor before running it. The private signing key is not included in the release; it is stored only as a GitHub Actions secret.

---

## Using the App

1. **Load XML** — click **Load XML File** and pick your file. The app auto-detects repeating tags. Choose the **Parent Tag** (the repeating element, e.g. `hero`) and **Target Tag** (the field to translate, e.g. `bio`), then click **Reload** to populate the table.

2. **Tag Presets** — save frequent tag combinations with a description via **💾 Save Preset**. Load them later with **📂 Load Preset**. Presets are stored in `tag_presets.json` in the app's user data folder.

3. **Select a provider** — use the **Translation Provider** dropdown in the right panel. For Google Translate no key is needed. For Gemini, DeepL, or Azure, click **API Key Configuration** and enter your key.

4. **Translate** — click **Translate All Pending** to process all entries in batch. Rows turn yellow while translating and green when done. To translate a single entry, select its row and click **Translate Selected Item**.

5. **Review** — select any row to read the original text and edit the translation in the right panel. Click **Confirm Selected Translation** to mark it as done, or **Confirm All Translations** to approve everything at once.

6. **Export** — use **Export Translated XML** to save a new file, or **💾 Save to Current File** to overwrite the original (a confirmation dialog appears). Saving in place auto-reloads the file.

[![YouTube Demo](https://img.shields.io/badge/YouTube-JSON%20export%20%2F%20import%20demo-red?logo=youtube&logoColor=white)](https://www.youtube.com/watch?v=ahnqpZrGQe0)

> Click the **ⓘ** button at the top-right of the tools panel for a built-in quick-reference guide.

---

## Translation Providers

| Provider | Requires Key | Type | Notes |
|---|---|---|---|
| Google Translate (Free) | No | Machine translation | May not sound natural; good for quick drafts |
| Google Gemini | Yes | Generative AI | Free-tier Flash models recommended; batch of 120 |
| Ollama (Local) | No | Generative AI | Requires local Ollama install; supports thinking mode |
| DeepL | Yes | Neural MT | High quality; free tier available |
| Microsoft Azure | Yes | Neural MT | Azure Cognitive Services subscription required |

**Gemini tips:** prefer **Gemini Flash Lite** or **Gemini Flash** on the free tier. Preview/Pro models (e.g. 2.5 Pro) may have zero free quota and return 429 errors. The 5-second inter-batch pause keeps free-tier usage within rate limits for most file sizes.

---

## Building a Standalone Executable

The project ships with a Nuitka build script for Windows:

```powershell
build_nuitka.bat
```

This activates `.venv` when present and produces `dist\main_qt.dist\STZXMLTranslator.exe`.
Static Nuitka flags live in `main_qt.py` as `# nuitka-project:` comments.
Only dynamic flags such as version, jobs, and report output are passed by `build_nuitka.bat`.

> QML files (`ui/**/*.qml`) are loaded at runtime — they must be included as data files, not compiled.

---

## Project Layout

```
main_qt.py               Entry point — PySide6 engine, context properties, theme init
core/
  app_controller.py      Facade: coordinates project, worker, config, and presets
  project.py             TranslationProject — entries, checkpoint, export/import
  translation_worker.py  Batch and single translation (background thread)
  extrator.py            XML text extraction
  injetor.py             XML translation injection
  tradutor_api.py        Provider adapters (Gemini, DeepL, Azure, Ollama, Google)
  i18n.py                Locale loader
ui/
  main.qml               Root ApplicationWindow
  theme.py               Colour token factory (_dark_base / _light_base) + 5 themes
  theme_controller.py    ThemeController — applies theme dict and updates QPalette
  viewmodel.py           AppViewModel — Python↔QML bridge (signals, slots, properties)
  components/
    LeftSidebar.qml      File loading, tag picker, presets, progress, export
    EditPanel.qml        Provider config, batch/single translate, review, scroll
    TranslationTable.qml Two-column table with status colours
    LogPanel.qml         Terminal-style log panel
    TagComboBox.qml      Editable searchable dropdown
    StyledComboBox.qml   Themed ComboBox with fixed scroll and highlight behaviour
    StyledScrollBar.qml  Thin tokenized scroll indicator
    GlossaryDialog.qml   Fixed-term glossary editor
    AppButton.qml        Themed button base
locales/                 UI strings — en_US, pt_BR, es_ES, fr_FR, ja_JP
assets/
  stz-xml.png            Source application icon
  icon.ico               Generated build icon (ignored by Git)
  settings.svg           Settings gear icon (colour-tokenized via ColorOverlay)
tests/
  test_theme.py          Theme token structure and palette tests (43 cases)
  test_locale_completeness.py  Locale key parity tests (19 cases)
  test_app_controller.py AppController unit tests
tag_presets.json         Saved tag presets (created at runtime)
config.json              User preferences — API keys, theme, language (created at runtime)
```

---

## Running Tests

```powershell
python -m pytest
```

All tests are in `tests/` and run without launching the GUI. The suite covers theme token structure, locale key parity across all five languages, and AppController business logic.

---

## Troubleshooting

| Problem | Solution |
|---|---|
| **White text on white context menu** | Ensure `QT_QPA_PLATFORM=windows:darkmode=2` is set — done automatically by `main_qt.py` on Win32. |
| **Tags not detected / empty dropdown** | The file may use namespaces or non-repeating elements. Type the tag name manually and click **Reload**. |
| **Translation never stops after Cancel** | Cancel stops the worker between batches. The current in-flight request finishes before stopping — HTTP calls cannot be interrupted mid-flight. |
| **API key error with Google Translate** | Google Translate (Free) requires no key. If the error persists, check that the selected provider in the dropdown is indeed **Google Translate (Free)**. |
| **Large executable size** | Expected for `--onefile`. Use `--standalone` for a folder-based distribution with faster startup. |
| **Locale not loading** | The JSON filename must match the locale code exactly (e.g. `pt_BR.json`) and contain valid JSON. |
| **Build failures on Windows** | Install the **Desktop development with C++** workload from Visual Studio Build Tools. |

---

## Contributing

Bug reports and pull requests are welcome. Please open an issue first to discuss major changes. Before submitting a PR:

```powershell
python -m pytest          # all tests must pass
ruff check .              # no lint errors
python main_qt.py         # verify the UI loads and locale files are intact
```

---

## Author

Created by [StarzynhoBR](https://github.com/StarzynhoBR).

---

## ⚖️ Licensing (Dual Licensing)

1. **Community Use (GPLv3):** Free for personal use and open-source projects. You are free to modify and distribute this software, provided that your changes remain open-source.

2. **Commercial Use:** For companies wishing to integrate this translation system into proprietary software, OEM distributions, or commercial interfaces, a separate license is required.

To acquire a commercial license, contact: [starzynhobr@gmail.com]
