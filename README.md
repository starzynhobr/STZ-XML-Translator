# STZ XML Translator

Desktop tool that helps modders and localization teams translate XML files for games or other structured content. Built with PySide6 + QML (FluentWinUI3 dark theme), it provides a modern interface to load XML files, preview original strings, apply AI translations in batch or individually, review results, and export the updated XML without altering the file's original structure.

## Features

- **Smart XML parser** — detects repeating elements automatically; extracts only the target text fields, preserving attributes, node order, and namespaces.
- **PySide6 / QML interface** — FluentWinUI3 dark theme, fluid layouts, searchable dropdowns.
- **AI translation** — batch translation via Google Gemini (120 items per call), plus sequential support for DeepL, Microsoft Azure, and Ollama (local).
- **Tag picker with presets** — auto-detect parent/child tags from the loaded XML; save named presets (`tag_presets.json`) for reuse across sessions.
- **Separate UI language and translation target** — change the app language independently from the language the AI translates into.
- **Checkpoint / resume** — progress is saved after each batch so you can interrupt and continue later.
- **Save in place** — overwrite the original file and auto-reload so the translated text becomes the new original for follow-up passes.
- **Glossary manager** — enforce project terminology via `scripts/glossario.json`.
- **Multi-language UI** — interface strings live in `locales/*.json`; five languages included (pt-BR, en-US, es-ES, fr-FR, ja-JP).

## Quick Start

Requirements:

- Python 3.12
- Windows 10/11 (FluentWinUI3 style requires Qt 6.7+)
- A translation provider API key (optional — required for AI translation)

```powershell
git clone https://github.com/StarzynhoBR/Game-XML-Translator.git
cd Game-XML-Translator
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main_qt.py
```

## Using the App

1. **Load XML** — click "Carregar XML" and pick your file. The app auto-detects repeating tags (parent candidates). Choose the **Parent Tag** (the repeating element, e.g. `hero`) and **Target Tag** (the field to translate, e.g. `bio`), then click **Recarregar** to populate the table.

2. **Tag Presets** — save frequent tag combinations with a description via "💾 Salvar Preset". Load them later with "📂 Carregar Preset". Presets are stored in `tag_presets.json` at the project root.

3. **Configure AI** — select a provider (Gemini, DeepL, Azure, or Ollama) and enter your API key via "Configurar API". For Gemini, free-tier Flash models are recommended.

4. **Translate** — click "Traduzir Todos os Pendentes" to process all entries in batch. Rows turn yellow while a batch is in flight; green when done. To translate a single entry, select its row and click "Traduzir Item Selecionado".

5. **Review** — select any row to read the original and edit the translation manually in the right panel. Click "Confirmar Tradução" to mark it as done.

6. **Export** — use "Exportar XML Traduzido" to save a new file, or "Salvar no Arquivo Atual" to overwrite the original (a confirmation dialog will appear). Saving in place automatically reloads the file so the translated text becomes the new original.

> The ⓘ button at the top-right of the tools panel shows a built-in quick-reference guide.

## Building a Standalone Executable

The project ships with a Nuitka build script for Windows:

```powershell
build_nuitka.bat
```

This activates `.venv`, upgrades Nuitka, and produces `dist\STZXMLTranslator.exe`.

Manual build (same flags used by the script):

```powershell
python -m nuitka ^
    --standalone --onefile ^
    --enable-plugin=pyside6 ^
    --windows-console-mode=disable ^
    --windows-icon-from-ico=assets/icon.ico ^
    --include-data-dir=ui=ui ^
    --include-data-dir=locales=locales ^
    --include-data-dir=assets=assets ^
    --include-data-dir=scripts=scripts ^
    --output-filename=STZXMLTranslator.exe ^
    --output-dir=dist ^
    main_qt.py
```

> QML files (`ui/**/*.qml`) must be included as data — they are loaded at runtime, not compiled by Nuitka.

## Project Layout

```
main_qt.py          Entry point (PySide6 + QML)
core/
  app_controller.py Facade: coordinates project, worker, config, presets
  project.py        TranslationProject — entries, checkpoint, export/import
  translation_worker.py  Batch/single AI translation (background thread)
  extrator.py       XML text extraction
  injetor.py        XML translation injection
  tradutor_api.py   Provider adapters (Gemini, DeepL, Azure, Ollama)
  i18n.py           Locale loader
ui/
  main.qml          Root ApplicationWindow
  theme.py          Central colour tokens (Theme.* context property)
  viewmodel.py      AppViewModel — Python↔QML bridge (signals/slots/properties)
  components/
    LeftSidebar.qml   File loading, tag picker, presets, progress, export
    EditPanel.qml     Provider config, batch/single translate, review
    TranslationTable.qml  Two-column table with status colours
    LogPanel.qml      Terminal-style log
    TagComboBox.qml   Editable searchable dropdown
    GlossaryDialog.qml
    AppButton.qml
locales/            UI strings (pt_BR, en_US, es_ES, fr_FR, ja_JP)
assets/             Application icon
scripts/            glossario.json (project terminology)
tag_presets.json    Saved tag presets (created at runtime)
config.json         User preferences (created at runtime)
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **White text on white context menu** | Ensure `QT_QPA_PLATFORM=windows:darkmode=2` is set (done automatically by `main_qt.py` on Win32). |
| **Tags not detected / empty dropdown** | The file may use namespaces or non-repeating elements. Type the tag name manually and click Recarregar. |
| **"AVISO: Tags encontradas, mas não continham texto"** | The auto-detected tag is a container, not a leaf field. Select a different parent or target tag. |
| **Translation never stops after Cancel** | Cancel stops the worker between batches. The current in-flight Gemini request finishes before stopping (HTTP calls can't be interrupted mid-flight). |
| **Large executable** | Expected for `--onefile`. Use `--standalone` for a folder-based distribution with faster startup. |
| **Locale not loading** | The JSON filename must match the locale code exactly (e.g. `pt_BR.json`) and contain valid JSON. |
| **Build failures on Windows** | Install the "Desktop development with C++" workload from Visual Studio Build Tools. |

## Author

Created by [StarzynhoBR](https://github.com/StarzynhoBR). Se voce reutilizar alguma parte deste projeto, mantenha os creditos.

## Contributing

Bug reports and pull requests are welcome. Please open an issue first to discuss major changes. For pull requests, run `python main_qt.py` locally to verify the UI and locale files still load correctly.

## ⚖️ Licensing (Dual Licensing)

1. **Community Use (GPLv3):** Free for personal use and open-source projects. You are free to modify and distribute this software, provided that your changes remain open-source.

2. **Commercial Use:** For companies wishing to integrate this translation system into proprietary software, OEM distributions, or commercial interfaces, a separate license is required.

To acquire a commercial license, contact: [starzynhobr@gmail.com]

### Gemini API Tips
- Free-tier models: prefer **Gemini Flash Lite** or **Gemini Flash** variants. Preview/Pro models (e.g. 2.5 Pro) may have zero free quota and return 429 errors.
- Batch size is fixed at 120 items per request. With a 5-second inter-batch pause the free tier handles large files without hitting rate limits in most cases.
