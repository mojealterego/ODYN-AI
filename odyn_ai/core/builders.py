from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from uuid import uuid4


SUPPORTED_PLATFORMS = {"web", "android"}
SUPPORTED_MODES = {"no_code", "code"}


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
    def __init__(self) -> None:
        self._apps: dict[str, AppDefinition] = {}

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
        return asdict(app) | {"files": sorted(app.files)}

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
        return {"path": clean, "content": content}
