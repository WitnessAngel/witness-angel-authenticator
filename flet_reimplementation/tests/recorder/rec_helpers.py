"""Shared helpers/fixtures of the recorder tests (imported explicitly: no conftest.py, to leave tests/conftest.py alone)."""
import json
import os
import shutil
import sys
from pathlib import Path
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

FIXTURES = Path(os.environ.get("WA_RECORDER_FIXTURES", ROOT.parents[1] / "witness-angel-recorder" / "specifications" / "fixtures"))
needs_fixtures = pytest.mark.skipif(not FIXTURES.is_dir(), reason="recorder spec fixtures not found (WA_RECORDER_FIXTURES)")

from wacryptolib.utilities import load_from_json_bytes  # noqa: E402

from waflet_components.config import AppConfig  # noqa: E402
from waflet_components.i18n import tr  # noqa: E402
from waflet_components.storage import compute_storage_roots, bootstrap_recorder_storage  # noqa: E402
import waflet_recorder  # noqa: E402,F401
from waflet_recorder.settings import RecorderSettings, CONFIG_DEFAULTS_PATH  # noqa: E402

GUARDIAN_A, GUARDIAN_B = UUID("104eba5c-7432-b37a-73dd-9bf61eadc87c"), UUID("104eba5c-972b-5915-03ba-f4f24b7ae687")


def passphrases():
    return json.loads((FIXTURES / "passphrases.json").read_text(encoding="utf8"))


def load_fixture_json(*parts):
    return load_from_json_bytes((FIXTURES.joinpath(*parts)).read_bytes())


@pytest.fixture(autouse=True)
def english():
    tr.lang = "en"
    yield
    tr.lang = "en"


@pytest.fixture
def roots(tmp_path):
    roots = compute_storage_roots("desktop", tmp_path / "home")
    bootstrap_recorder_storage(roots)
    return roots


@pytest.fixture
def pool_roots(roots):
    """Roots whose keystore pool is a copy of fixtures/keystore_pool (guardian A with private keys, B public only)."""
    shutil.rmtree(roots.keystore_pool_dir)
    shutil.copytree(FIXTURES / "keystore_pool", roots.keystore_pool_dir)
    return roots


@pytest.fixture
def pool(pool_roots):
    from waflet_recorder.guardians import open_keystore_pool
    return open_keystore_pool(pool_roots)


def make_settings(roots, is_pi=False, **overrides):
    """overrides: {"section.key": value}"""
    config = AppConfig(roots.internal_app_root / "warecorder_config.ini", CONFIG_DEFAULTS_PATH)
    for dotted, value in overrides.items():
        section, key = dotted.split(".")
        config.set(section, key, value, save=False)
    return RecorderSettings(config, roots, is_raspberry_pi=is_pi)
