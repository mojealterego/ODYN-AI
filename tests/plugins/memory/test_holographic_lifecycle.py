"""Behavioral regressions found while reviewing the standalone memory provider."""

import shutil
import sqlite3
from unittest.mock import patch

import pytest
import yaml

from plugins.memory.holographic import HolographicMemoryProvider


@pytest.mark.parametrize("setting", [False, "false", "off", "0", "FALSE"])
def test_disabled_auto_extract_does_not_store_user_preferences(tmp_path, setting):
    provider = HolographicMemoryProvider(
        {"db_path": str(tmp_path / "facts.db"), "auto_extract": setting}
    )
    provider.initialize("session")
    store = provider._store
    try:
        provider.on_session_end([{"role": "user", "content": "I prefer a quiet editor."}])
        assert store.list_facts() == []
    finally:
        provider.shutdown()
        store.close()


@pytest.mark.parametrize("setting", [True, "true", "yes", "on"])
def test_enabled_auto_extract_stores_user_preferences(tmp_path, setting):
    provider = HolographicMemoryProvider(
        {"db_path": str(tmp_path / "facts.db"), "auto_extract": setting}
    )
    provider.initialize("session")
    store = provider._store
    try:
        provider.on_session_end([{"role": "user", "content": "I prefer a quiet editor."}])
        facts = store.list_facts()
        assert len(facts) == 1
        assert facts[0]["content"] == "I prefer a quiet editor."
    finally:
        provider.shutdown()
        store.close()


def test_shutdown_closes_sqlite_even_when_another_reference_exists(tmp_path):
    provider = HolographicMemoryProvider({"db_path": str(tmp_path / "facts.db")})
    provider.initialize("session")
    connection = provider._store._conn
    try:
        provider.shutdown()
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT COUNT(*) FROM facts")
        provider.shutdown()  # Repeated gateway cleanup is harmless.
    finally:
        connection.close()


def test_cloned_profile_opens_its_own_default_database(tmp_path):
    original_home = tmp_path / "original"
    cloned_home = tmp_path / "cloned"
    original_home.mkdir()
    cloned_home.mkdir()
    original_config = original_home / "config.yaml"
    original_config.write_text("model: unchanged\n", encoding="utf-8")
    values = {"db_path": str(original_home / "memory_store.db"), "auto_extract": "false"}
    with patch("hermes_constants.get_hermes_home", return_value=original_home):
        provider = HolographicMemoryProvider({"auto_extract": False})
        provider.save_config(values, str(original_home))
        saved = yaml.safe_load(original_config.read_text(encoding="utf-8"))
        provider = HolographicMemoryProvider(saved["plugins"]["hermes-memory-store"])
        provider.initialize("original-session")
        store = provider._store
        try:
            store.add_fact("Only the original profile knows this fact.")
        finally:
            provider.shutdown()
            store.close()
    assert saved["model"] == "unchanged"
    assert values["db_path"] == str(original_home / "memory_store.db")
    shutil.copy2(original_config, cloned_home / "config.yaml")
    with patch("hermes_constants.get_hermes_home", return_value=cloned_home):
        cloned_config = yaml.safe_load((cloned_home / "config.yaml").read_text(encoding="utf-8"))
        clone = HolographicMemoryProvider(cloned_config["plugins"]["hermes-memory-store"])
        clone.initialize("cloned-session")
        store = clone._store
        try:
            assert store.db_path == cloned_home / "memory_store.db"
            assert store.list_facts() == []
        finally:
            clone.shutdown()
            store.close()


def test_default_schema_resolves_against_profile_at_initialization(tmp_path):
    first_home = tmp_path / "first"
    second_home = tmp_path / "second"
    with patch("hermes_constants.get_hermes_home", return_value=first_home):
        schema = HolographicMemoryProvider({"auto_extract": False}).get_config_schema()
    values = {field["key"]: field["default"] for field in schema}
    with patch("hermes_constants.get_hermes_home", return_value=second_home):
        provider = HolographicMemoryProvider(values)
        provider.initialize("second-session")
        store = provider._store
        try:
            assert store.db_path == second_home / "memory_store.db"
        finally:
            provider.shutdown()
            store.close()


def test_custom_database_path_is_preserved_when_saving(tmp_path):
    profile = tmp_path / "profile"
    profile.mkdir()
    custom_db = tmp_path / "deliberately-shared.db"
    values = {"db_path": str(custom_db)}
    HolographicMemoryProvider({"auto_extract": False}).save_config(values, str(profile))
    saved = yaml.safe_load((profile / "config.yaml").read_text(encoding="utf-8"))
    assert saved["plugins"]["hermes-memory-store"]["db_path"] == str(custom_db)
