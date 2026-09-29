from __future__ import annotations

from dataclasses import asdict, dataclass, field
from html import escape
from pathlib import PurePosixPath
from uuid import uuid4

from odyn_ai.core.state import JsonStore


SUPPORTED_PLATFORMS = {"web", "android"}
SUPPORTED_MODES = {"no_code", "code"}
FORM_FIELD_TYPES = {"text", "email", "number", "tel", "date", "textarea", "select", "checkbox", "radio", "file"}


@dataclass
class AppDefinition:
    app_id: str
    name: str
    description: str
    agent_id: str
    language: str = "pl"
    platform: str = "web"
    mode: str = "no_code"
    files: dict[str, str] = field(default_factory=dict)


def _web_files(name: str) -> dict[str, str]:
    return {
        "package.json": '{\n  "name": "' + name.lower().replace(" ", "-") + '",\n  "private": true,\n  "scripts": { "dev": "vite", "build": "vite build", "test": "vitest run" }\n}',
        "index.html": "<!doctype html>\n<html lang=\"pl\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>" + name + "</title></head><body><div id=\"root\"></div><script type=\"module\" src=\"/src/main.tsx\"></script></body></html>",
        "src/main.tsx": "import React from 'react';\nimport { createRoot } from 'react-dom/client';\nimport App from './App';\ncreateRoot(document.getElementById('root')!).render(<App />);",
        "src/App.tsx": "export default function App() { return <main><h1>" + name + "</h1></main>; }",
    }


def _android_files(name: str) -> dict[str, str]:
    app_name = name.replace('"', "")
    return {
        "settings.gradle.kts": 'pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }\ndependencyResolutionManagement { repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS); repositories { google(); mavenCentral() } }\nrootProject.name = "' + app_name + '"\ninclude(":app")',
        "build.gradle.kts": 'plugins { id("com.android.application") version "8.7.3" apply false\n    id("org.jetbrains.kotlin.android") version "2.1.0" apply false\n    id("org.jetbrains.kotlin.plugin.compose") version "2.1.0" apply false\n}',
        "app/build.gradle.kts": 'plugins { id("com.android.application")\n    id("org.jetbrains.kotlin.android")\n    id("org.jetbrains.kotlin.plugin.compose") }\n\nandroid { namespace = "ai.odyn.generated"; compileSdk = 35\n    defaultConfig { applicationId = "ai.odyn.generated"; minSdk = 26; targetSdk = 35; versionCode = 1; versionName = "1.0" }\n}',
        "app/src/main/AndroidManifest.xml": '<manifest xmlns:android="http://schemas.android.com/apk/res/android"><application android:theme="@style/Theme.App"><activity android:name=".MainActivity" android:exported="true"><intent-filter><action android:name="android.intent.action.MAIN"/><category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity></application></manifest>',
        "app/src/main/java/ai/odyn/generated/MainActivity.kt": 'package ai.odyn.generated\n\nimport android.os.Bundle\nimport androidx.activity.ComponentActivity\nimport androidx.activity.compose.setContent\nimport androidx.compose.material3.Text\n\nclass MainActivity : ComponentActivity() { override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState); setContent { Text("' + app_name + '") } } }',
        "app/src/main/res/values/styles.xml": '<resources><style name="Theme.App" parent="android:style/Theme.Material.Light.NoActionBar"/></resources>',
    }


class AppBuilder:
    def __init__(self, data_dir: str | None = None) -> None:
        self._store = JsonStore("apps", data_dir)
        raw = self._store.load({"apps": [], "forms": []})
        self._apps = {item["app_id"]: AppDefinition(**item) for item in raw.get("apps", []) if isinstance(item, dict) and item.get("app_id")}
        self._forms = {item["form_id"]: item for item in raw.get("forms", []) if isinstance(item, dict) and item.get("form_id")}

    def _persist(self) -> None:
        self._store.save({
            "apps": [asdict(app) for app in self._apps.values()],
            "forms": list(self._forms.values()),
        })

    def list_apps(self) -> list[dict[str, object]]:
        return [asdict(a) | {"files": sorted(a.files)} for a in self._apps.values()]

    def create(
        self,
        name: str,
        description: str,
        agent_id: str,
        language: str = "pl",
        platform: str = "web",
        mode: str = "no_code",
    ) -> dict[str, object]:
        if not name.strip():
            raise ValueError("Nazwa aplikacji jest wymagana")
        if platform not in SUPPORTED_PLATFORMS:
            raise ValueError("Obsługiwane platformy: web albo android.")
        if mode not in SUPPORTED_MODES:
            raise ValueError("Tryb aplikacji musi być: no_code albo code.")
        app_id = f"app_{uuid4().hex[:12]}"
        files = _android_files(name.strip()) if platform == "android" else _web_files(name.strip())
        app = AppDefinition(
            app_id,
            name.strip(),
            description.strip(),
            agent_id,
            language if language in {"pl", "en"} else "pl",
            platform,
            mode,
            files,
        )
        self._apps[app.app_id] = app
        self._persist()
        return asdict(app) | {"files": sorted(app.files)}

    def create_form(self, app_id: str, name: str) -> dict[str, object]:
        app = self._get(app_id)
        if app.mode != "no_code":
            raise ValueError("Formularze No Code są dostępne w trybie no_code.")
        if not name.strip():
            raise ValueError("Nazwa formularza jest wymagana.")
        form = {"form_id": f"form_{uuid4().hex[:12]}", "app_id": app_id, "name": name.strip(), "fields": []}
        self._forms[form["form_id"]] = form
        self._persist()
        return form

    def get_form(self, form_id: str) -> dict[str, object]:
        try:
            return self._forms[form_id]
        except KeyError as exc:
            raise ValueError("Nie znaleziono formularza.") from exc

    def add_form_field(self, form_id: str, field_type: str, label: str, *, required: bool = False, validation: str = "", default: str = "", options: list[str] | None = None) -> dict[str, object]:
        form = self.get_form(form_id)
        if field_type not in FORM_FIELD_TYPES:
            raise ValueError("Nieobsługiwany typ pola formularza.")
        if not label.strip():
            raise ValueError("Etykieta pola jest wymagana.")
        if field_type in {"select", "radio"} and not options:
            raise ValueError("To pole wymaga listy opcji.")
        field = {"field_id": f"field_{uuid4().hex[:10]}", "type": field_type, "label": label.strip(), "required": bool(required), "validation": validation.strip(), "default": default, "options": list(options or [])}
        form["fields"].append(field)
        self._persist()
        return field

    def form_preview(self, form_id: str) -> dict[str, object]:
        form = self.get_form(form_id)
        html = [f'<form data-form-id="{escape(str(form["form_id"]), quote=True)}"><h2>{escape(str(form["name"]))}</h2>']
        for field in form["fields"]:
            required = " required" if field["required"] else ""
            if field["type"] == "select":
                options = "".join(f'<option>{escape(str(option))}</option>' for option in field["options"])
                html.append(f'<label>{field["label"]}<select{required}>{options}</select></label>')
            elif field["type"] == "radio":
                controls = "".join(f'<label><input type="radio" name="{escape(str(field["field_id"]), quote=True)}">{escape(str(option))}</label>' for option in field["options"])
                html.append(f'<fieldset><legend>{escape(str(field["label"]))}</legend>{controls}</fieldset>')
            elif field["type"] == "textarea":
                html.append(f'<label>{escape(str(field["label"]))}<textarea{required}>{escape(str(field["default"]))}</textarea></label>')
            elif field["type"] == "checkbox":
                html.append(f'<label><input type="checkbox"{required}>{escape(str(field["label"]))}</label>')
            else:
                html.append(f'<label>{escape(str(field["label"]))}<input type="{escape(str(field["type"]), quote=True)}" value="{escape(str(field["default"]), quote=True)}"{required}></label>')
        html.append("</form>")
        return {"form_id": form_id, "html": "\n".join(html)}
    def _get(self, app_id: str) -> AppDefinition:
        try:
            return self._apps[app_id]
        except KeyError as exc:
            raise ValueError("Nie znaleziono projektu aplikacji.") from exc

    def workspace(self, app_id: str) -> dict[str, object]:
        app = self._get(app_id)
        return {
            "app_id": app.app_id,
            "name": app.name,
            "platform": app.platform,
            "mode": app.mode,
            "files": dict(app.files),
        }

    def read_file(self, app_id: str) -> dict[str, object]:
        return self.workspace(app_id)

    def write_file(self, app_id: str, path: str, content: str) -> dict[str, object]:
        app = self._get(app_id)
        clean = str(PurePosixPath(path))
        if clean in {".", ".."} or clean.startswith("../") or "/../" in clean:
            raise ValueError("Nieprawidłowa ścieżka pliku.")
        if not clean or clean.startswith("/"):
            raise ValueError("Ścieżka pliku musi być względna.")
        app.files[clean] = content
        self._persist()
        return {"path": clean, "content": content}
