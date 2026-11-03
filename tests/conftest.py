"""Keep every test's user data (config, checkpoints, translations.db) out of the repository."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_user_data(tmp_path, monkeypatch):
    # Outside a packaged build user data lives in the working directory; give
    # each test its own. Tests that need a specific folder still set one.
    monkeypatch.chdir(tmp_path)
