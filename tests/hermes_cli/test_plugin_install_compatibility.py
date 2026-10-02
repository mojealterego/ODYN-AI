"""Install failures preserve existing plugins and explain the required runtime."""

from pathlib import Path
from unittest.mock import patch

import pytest

from hermes_cli.plugins_cmd import PluginOperationError, _install_plugin_core


def _clone_fixture(files):
    def clone(args, **kwargs):
        destination = Path(args[-1])
        destination.mkdir()
        for name, content in files.items():
            (destination / name).write_text(content, encoding="utf-8")
        return type("CloneResult", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    return clone


@pytest.mark.parametrize(
    "files,message",
    [
        ({"plugin.json": '{"name":"compatible-name"}', "mcp.json": "{}"}, "plugin.json"),
        ({"plugin.js": "export default {};"}, "Desktop"),
    ],
)
def test_unsupported_plugin_does_not_replace_existing_install(tmp_path, files, message):
    plugins = tmp_path / "plugins"
    existing = plugins / "compatible-name"
    existing.mkdir(parents=True)
    marker = existing / "keep.txt"
    marker.write_text("Existing plugin still works", encoding="utf-8")
    with patch("hermes_cli.plugins_cmd._plugins_dir", return_value=plugins), \
         patch("hermes_cli.plugins_cmd._resolve_git_executable", return_value="git"), \
         patch("hermes_cli.plugins_cmd.subprocess.run", side_effect=_clone_fixture(files)):
        with pytest.raises(PluginOperationError, match=message):
            _install_plugin_core("owner/compatible-name", force=True)
    assert marker.read_text(encoding="utf-8") == "Existing plugin still works"
    assert sorted(p.name for p in plugins.iterdir()) == ["compatible-name"]


def test_yml_manifest_uses_canonical_name_and_retains_metadata(tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    files = {"plugin.yml": "name: canonical-name\nversion: '1.0'\n", "__init__.py": ""}
    with patch("hermes_cli.plugins_cmd._plugins_dir", return_value=plugins), \
         patch("hermes_cli.plugins_cmd._resolve_git_executable", return_value="git"), \
         patch("hermes_cli.plugins_cmd.subprocess.run", side_effect=_clone_fixture(files)):
        target, manifest, name = _install_plugin_core("owner/different-repo-name", force=False)
    assert target == plugins / "canonical-name"
    assert name == "canonical-name"
    assert manifest["version"] == "1.0"


def test_native_plugin_can_also_include_portable_metadata(tmp_path):
    plugins = tmp_path / "plugins"
    plugins.mkdir()
    files = {
        "plugin.yaml": "name: native-plugin\n",
        "__init__.py": "",
        "plugin.json": '{"name":"native-plugin"}',
        "plugin.js": "export default {};",
    }
    with patch("hermes_cli.plugins_cmd._plugins_dir", return_value=plugins), \
         patch("hermes_cli.plugins_cmd._resolve_git_executable", return_value="git"), \
         patch("hermes_cli.plugins_cmd.subprocess.run", side_effect=_clone_fixture(files)):
        target, _, name = _install_plugin_core("owner/native-plugin", force=False)
    assert name == "native-plugin"
    assert (target / "plugin.yaml").is_file()
