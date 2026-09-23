from unittest.mock import MagicMock, patch

from core.project import TranslationEntry, TranslationProject
from core.translation_worker import TranslationWorker


def test_gemini_batch_protects_and_restores_glossary_terms():
    project = TranslationProject()
    worker = TranslationWorker(
        project=project,
        config={
            "api_key": "fake",
            "model": "gemini-test",
            "target_lang": "pt",
            "target_label": "Portuguese (Brazil)",
        },
        on_entry_translated=lambda *_: None,
        on_log=lambda _: None,
        on_done=lambda: None,
    )
    entry = TranslationEntry(
        xpath="/root/item[1]/bio[1]",
        original="The Sword is ready",
        source_tag="bio",
        context={"dispName": "WHIPLASH"},
    )
    model = MagicMock()
    model.generate_content.return_value.text = (
        "[ID: /root/item[1]/bio[1]]\nTEXT TO TRANSLATE:\n"
        "A STZGLOSSARYTOKEN0END está pronta\n---"
    )

    with (
        patch("core.translation_worker.get_gemini_model", return_value=model),
        patch(
            "core.translation_worker.protect_glossary_for_ai",
            return_value=("The STZGLOSSARYTOKEN0END is ready", {"STZGLOSSARYTOKEN0END": "Espada"}),
        ),
    ):
        result = worker._translate_batch_gemini([entry])

    prompt = model.generate_content.call_args.args[0]
    assert "The STZGLOSSARYTOKEN0END is ready" in prompt
    assert "Translate all surrounding text" in prompt
    assert '"dispName": "WHIPLASH"' in prompt
    assert "Do not translate or return" in prompt
    assert result == {"/root/item[1]/bio[1]": "A Espada está pronta"}


def test_worker_passes_entry_context_to_individual_provider():
    project = TranslationProject()
    project.entries = {
        "/a": TranslationEntry(
            "/a",
            "Gifted technician.",
            source_tag="bio",
            context={"dispName": "WHIPLASH"},
        )
    }
    worker = TranslationWorker(
        project=project,
        config={"service": "DeepL", "target_lang": "pt"},
        on_entry_translated=lambda *_: None,
        on_log=lambda _: None,
        on_done=lambda: None,
    )

    with (
        patch("core.translation_worker.translate_text", return_value="Técnico talentoso.") as call,
        patch.object(project, "load_checkpoint_with_fallback", return_value=0),
        patch.object(project, "save_checkpoint", return_value=True),
    ):
        worker._run()

    sent_config = call.call_args.args[2]
    assert sent_config["source_tag"] == "bio"
    assert sent_config["entry_context"] == {"dispName": "WHIPLASH"}


def test_worker_warns_once_when_provider_cannot_use_context():
    project = TranslationProject()
    project.entries = {
        "/a": TranslationEntry("/a", "A", context={"name": "First"}),
        "/b": TranslationEntry("/b", "B", context={"name": "Second"}),
    }
    logs = []
    worker = TranslationWorker(
        project=project,
        config={"service": "Google Translate (Free)"},
        on_entry_translated=lambda *_: None,
        on_log=logs.append,
        on_done=lambda: None,
    )

    with (
        patch("core.translation_worker.translate_batch_google_free", return_value={"/a": "AA", "/b": "BB"}),
        patch.object(project, "load_checkpoint_with_fallback", return_value=0),
        patch.object(project, "save_checkpoint", return_value=True),
    ):
        worker._run()

    context_warnings = [message for message in logs if "contexto" in message.lower()]
    assert len(context_warnings) == 1
    assert "Google Translate (Free)" in context_warnings[0]


def test_worker_limits_batch_to_selected_xpaths():
    project = TranslationProject()
    project.entries = {
        "/a": TranslationEntry("/a", "A"),
        "/b": TranslationEntry("/b", "B", "Old", "done"),
        "/c": TranslationEntry("/c", "C"),
    }
    translated = []
    worker = TranslationWorker(
        project=project,
        config={
            "service": "Gemini",
            "selected_xpaths": ["/a", "/b"],
            "include_done": True,
        },
        on_entry_translated=lambda xpath, _text: translated.append(xpath),
        on_log=lambda _: None,
        on_done=lambda: None,
    )

    with (
        patch.object(worker, "_translate_batch_gemini", return_value={"/a": "AA", "/b": "BB"}),
        patch.object(project, "load_checkpoint_with_fallback", return_value=0),
        patch.object(project, "save_checkpoint", return_value=True),
    ):
        worker._run()

    assert translated == ["/a", "/b"]
    assert project.entries["/a"].translation == "AA"
    assert project.entries["/b"].translation == "BB"
    assert project.entries["/c"].translation == ""
