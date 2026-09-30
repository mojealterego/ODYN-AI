<p align="center">
  <img src="assets/banner.png" alt="ODYN AI" width="100%">
</p>

<h1 align="center">ODYN AI 🐦‍⬛</h1>

<p align="center">
  <strong>Local-first cognitive AI engineering environment powered by GGUF.</strong><br>
  Polish-native • Dual GGUF • Cognitive Engine • Agents Builder • App Builder • Autonomous Build Pipeline
</p>

<p align="center">
  <img src="https://img.shields.io/badge/AI-Local--First-111827?style=for-the-badge" alt="Local First">
  <img src="https://img.shields.io/badge/Models-GGUF-374151?style=for-the-badge" alt="GGUF">
  <img src="https://img.shields.io/badge/Language-Polski-2563EB?style=for-the-badge" alt="Polish">
  <img src="https://img.shields.io/badge/Architecture-Cognitive%20AI-7C3AED?style=for-the-badge" alt="Cognitive AI">
  <img src="https://img.shields.io/badge/License-MIT-16A34A?style=for-the-badge" alt="MIT License">
</p>

---

## Czym jest ODYN AI?

**ODYN AI** to lokalne środowisko AI do uruchamiania modeli GGUF, budowania agentów, tworzenia aplikacji i wykonywania zadań programistycznych z wykorzystaniem pamięci doświadczeń oraz warstwy poznawczej.

Projekt jest projektowany jako **system lokalny i autonomiczny**, a nie jako kolejny interfejs czatu.

Główne elementy:

- **DualGGUFEngine** — równoległa praca z modelem głównym i pomocniczym.
- **CognitiveEngine** — planowanie, Graph of Thought, ocena strategii, refleksja i modulacja inferencji.
- **AgentExperienceMemory** — pamięć doświadczeń oparta o historię wykonania, sukcesów, porażek i korekt.
- **Bitemporal Memory** — trwała pamięć z osiami czasu valid-time i transaction-time.
- **RAG Memory** — opcjonalne indeksowanie doświadczeń wektorowych.
- **CodingAgent** — agent programistyczny operujący na rzeczywistych plikach projektu.
- **AutonomousBuildOrchestrator** — pełny cykl: zadanie → plan → zmiana → test → korekta → build → sukces.
- **ExecutionEngine** — wykonywanie testów, buildów i operacji na projektach web/Android.
- **GitHub Integration** — odczyt repozytoriów i zapisywanie zmian przez Git Data API.
- **Voice Command API** — sterowanie poleceniami głosowymi.
- **Agents / App Builder** — fundament pod budowanie agentów i aplikacji bez konieczności ręcznego pisania całego kodu.

---

## Architektura

```text
                         ┌──────────────────────┐
                         │      ODYN AI UI      │
                         │ Polish / Voice / API │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │   AutonomousBuildOrchestrator │
                    └───────────────┬───────────────┘
                                    │
              ┌─────────────────────▼─────────────────────┐
              │              CognitiveEngine              │
              │                                            │
              │ Graph of Thought                           │
              │ Strategy Planning                           │
              │ Reflexion                                  │
              │ Cognitive Modulation                       │
              └───────────────┬────────────────────────────┘
                              │
                 environmental_stress
                              │
                    ┌─────────▼─────────┐
                    │ Inference Policy  │
                    │ temperature       │
                    │ top_p             │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │    CodingAgent    │
                    └─────────┬─────────┘
                              │
                 ┌────────────▼────────────┐
                 │    DualGGUFEngine       │
                 │                         │
                 │ MAIN MODEL + DRAFT      │
                 │ speculative decoding    │
                 └────────────┬────────────┘
                              │
                 ┌────────────▼────────────┐
                 │ ExecutionEngine         │
                 │ test / build / run      │
                 └────────────┬────────────┘
                              │
               ┌──────────────▼──────────────┐
               │ Experience + Bitemporal     │
               │ Memory + optional RAG       │
               └─────────────────────────────┘
```

---

## Kluczowa cecha: AI uczy się z wykonania

ODYN AI nie traktuje każdego zadania jako izolowanej rozmowy.

Historia wykonania może zawierać:

```text
TASK
  ↓
COGNITIVE PLAN
  ↓
SELECTED STRATEGY
  ↓
CODING DECISION
  ↓
CODE CHANGE
  ↓
TEST / BUILD
  ├── SUCCESS
  │     ↓
  │  SUCCESSFUL PROCEDURE
  │
  └── FAILURE
        ↓
     REFLEXION
        ↓
     CORRECTION
        ↓
     RETRY
        ↓
     SUCCESS / FAILURE
```

Na tej podstawie wyliczany jest **environmental stress** — poziom presji wynikającej z aktualnej historii wykonania.

Wysokie obciążenie może prowadzić do bardziej konserwatywnej inferencji:

```text
history
   ↓
environmental_stress
   ↓
cognitive_modulation()
   ↓
temperature / top_p
   ↓
DualGGUFEngine
```

Parametry są stosowane per request, bez mutowania globalnej konfiguracji modelu.

---

## DualGGUFEngine

Silnik obsługuje dwa modele GGUF:

```text
MAIN MODEL
    │
    ├── główna odpowiedź
    │
    └── reasoning / coding
             ▲
             │
DRAFT MODEL ─┘
```

Domyślna konfiguracja projektu wykorzystuje:

```text
MAIN_MODEL_FILENAME  = model_glowny_normany.gguf
DRAFT_MODEL_FILENAME = model_pomocniczy_maly.gguf

n_ctx       = 8192
temperature = 0.65
top_p       = 0.90
top_k       = 40
```

Parametry inferencji mogą być nadpisywane dla pojedynczego żądania przez warstwę Cognitive Engine.

---

## Cognitive Engine

Warstwa poznawcza znajduje się w:

```text
nexus_core/reasoning/cognitive_engine.py
```

Obecne komponenty:

- **ThoughtNode**
- **CognitiveEvaluation**
- **Graph of Thought**
- **strategy planning**
- **reflexion loop**
- **cognitive modulation**
- **embedding-based similarity evaluation**
- **bounded adversarial search**
- **build planning**

Cognitive Engine przechowuje obserwowalne wyniki procesu decyzyjnego: wybrane strategie, oceny, zależności, błędy i rezultaty. Nie jest to zapis prywatnego chain-of-thought modelu.

> Implementacja wyszukiwania jest ograniczonym wyszukiwaniem adversarial alpha-beta z opcjonalnym rolloutem; nie jest deklarowana jako pełne stochastyczne MCTS. Ocena embeddingów jest inspirowana podejściem latent-space/JEPA, a nie pełną implementacją JEPA.

---

## Pamięć

ODYN AI posiada kilka poziomów pamięci:

### Bitemporal Memory

```text
nexus_core/memory/
├── bitemporal_store.py
└── tests/
    └── test_bitemporal_store.py
```

Obsługiwane są:

- valid-time,
- transaction-time,
- append-only revisions,
- `replaces_id`,
- point-in-time recovery,
- working memory,
- long-term archive,
- procedural skills,
- graph relations,
- SQLite WAL,
- gzip archive.

### Experience Memory

```text
odyn_ai/core/experience_memory.py
```

Zapamiętywane są m.in.:

- zadania,
- decyzje,
- zmiany kodu,
- wyniki testów,
- wyniki buildów,
- korekty,
- refleksje,
- skuteczne procedury,
- wybrane strategie poznawcze.

### RAG

RAG jest opcjonalny.

Konfiguracja:

```bash
ODYN_RAG_EMBEDDING_MODEL=/path/to/embedding-model
ODYN_RAG_MEMORY_PATH=odyn_rag_memory.json
```

Bez modelu embeddingowego trwała pamięć doświadczeń nadal działa.

---

## Autonomous Build Pipeline

Główny przepływ:

```text
User task
   ↓
Load project workspace
   ↓
Recall experience
   ↓
Calculate environmental stress
   ↓
Cognitive strategy planning
   ↓
Select strategy
   ↓
CodingAgent
   ↓
Apply changes
   ↓
TEST
   │
   ├── failure → reflexion → correction → retry
   │
   └── success
           ↓
         BUILD
           │
           ├── failure → correction → retry
           │
           └── success
                   ↓
            Successful procedure
                   ↓
             Optional GitHub commit
```

To jest podstawowa jednostka autonomicznej pracy ODYN AI.

---

## Coding Agent

Plik:

```text
odyn_ai/core/coding_agent.py
```

Agent operuje na kontrolowanym kontrakcie JSON:

```json
{
  "summary": "Opis wykonanej zmiany",
  "changes": [
    {
      "path": "relative/path/to/file",
      "content": "pełna zawartość pliku"
    }
  ]
}
```

Obowiązują ograniczenia bezpieczeństwa:

- wyłącznie ścieżki względne,
- brak `..`,
- brak ścieżek absolutnych,
- limit liczby zmienianych plików,
- limit rozmiaru pojedynczego pliku,
- walidacja odpowiedzi przed zastosowaniem.

---

## Execution Engine

```text
odyn_ai/core/execution.py
```

Obsługiwane platformy:

- Web
- Android

Obsługiwane operacje:

- `run`
- `test`
- `build`

Przykładowe zadania Android:

```bash
./gradlew :app:installDebug
./gradlew assembleDebug
./gradlew test
```

Przykładowe zadania Web:

```bash
npm run dev -- --host 127.0.0.1
npm run build
npm test
```

Wykonywanie jest ograniczone polityką czasu, ścieżek i środowiska. Execution Engine nie jest obecnie pełnym sandboxem systemowym.

---

## GitHub Integration

ODYN AI może współpracować z repozytoriami GitHub poprzez Git Data API.

Warstwa:

```text
odyn_ai/core/github_integration.py
```

Obsługiwane operacje obejmują:

- odczyt repozytorium,
- rozwiązywanie branchy,
- pobieranie blobów,
- tworzenie drzewa,
- tworzenie commitów,
- aktualizację refa branchu.

Token:

```bash
export ODYN_GITHUB_TOKEN="..."
```

---

## API

Główne API znajduje się w:

```text
odyn_ai/api/server.py
```

Dostępne są m.in.:

```text
/api/apps/{app_id}/agent/edit
/api/apps/{app_id}/execute
/api/apps/{app_id}/autonomous-build
/api/apps/{app_id}/github/commit
/api/voice/command
```

Voice Command API pozwala przekazać polecenie głosowe do warstwy budowania autonomicznego.

---

## Voice / STT

ODYN AI posiada warstwę poleceń głosowych przeznaczoną do obsługi zadań takich jak:

```text
„Zbuduj aplikację…”

„Dodaj ekran logowania…”

„Uruchom testy…”

„Popraw błąd i zbuduj ponownie…”
```

Warstwa głosowa jest wejściem do tego samego orchestratora, którego można używać przez API.

---

## Agents Builder

Docelowym elementem ODYN AI jest środowisko tworzenia agentów bez konieczności ręcznego budowania całej infrastruktury.

Kierunek architektury:

```text
Agent Definition
      ↓
System Prompt
      ↓
Tools
      ↓
Memory
      ↓
Execution Policy
      ↓
Model / GGUF
      ↓
Agent Runtime
```

Agent może następnie korzystać z tych samych mechanizmów pamięci, inferencji, wykonania i GitHub, które wykorzystuje AutonomousBuildOrchestrator.

---

## App Builder

ODYN AI jest rozwijany również jako **No-Code / Low-Code App Builder**.

Docelowy przepływ:

```text
Opis aplikacji
      ↓
Cognitive Planning
      ↓
Project Scaffold
      ↓
Coding Agent
      ↓
Assets / UI / Logic
      ↓
Test
      ↓
Build
      ↓
APK / Web Artifact
      ↓
GitHub
```

Warstwa ta ma wykorzystywać istniejący Execution Engine i Coding Agent zamiast tworzyć drugi, niezależny system wykonywania.

---

## Struktura projektu

```text
ODYN-AI/
├── odyn_ai/
│   ├── api/
│   │   └── server.py
│   ├── core/
│   │   ├── coding_agent.py
│   │   ├── engine.py
│   │   ├── execution.py
│   │   ├── experience_memory.py
│   │   ├── github_integration.py
│   │   ├── orchestrator.py
│   │   └── rag_memory.py
│   ├── ui/
│   └── tests/
│
├── nexus_core/
│   ├── memory/
│   │   ├── bitemporal_store.py
│   │   └── tests/
│   └── reasoning/
│       ├── cognitive_engine.py
│       └── tests/
│
├── assets/
├── requirements.txt
├── requirements_test.txt
└── README.md
```

---

## Konfiguracja modeli

Przykładowe ustawienia:

```python
MAIN_MODEL_FILENAME = "model_glowny_normany.gguf"
DRAFT_MODEL_FILENAME = "model_pomocniczy_maly.gguf"

N_CTX = 8192
N_THREADS = max(1, os.cpu_count() - 2)

N_GPU_LAYERS_MAIN = -1
N_GPU_LAYERS_DRAFT = -1

TEMPERATURE = 0.65
TOP_P = 0.90
TOP_K = 40
```

Nazwy plików modeli są konfigurowalne. Modele GGUF nie są dostarczane w repozytorium.

---

## Instalacja developerska

```bash
git clone https://github.com/mojealterego/ODYN-AI.git
cd ODYN-AI

python -m venv .venv
source .venv/bin/activate

pip install -r odyn_ai/requirements.txt
pip install -r odyn_ai/requirements_test.txt
```

Uruchomienie API:

```bash
python -m uvicorn odyn_ai.api.server:app --host 127.0.0.1 --port 8000
```

Dokładne zależności mogą różnić się zależnie od backendu GGUF i środowiska uruchomieniowego.

---

## Testy

Testy obejmują m.in.:

- Cognitive Engine,
- bitemporal memory,
- experience memory,
- environmental stress,
- inference modulation,
- CodingAgent,
- AutonomousBuildOrchestrator,
- pełny cykl pamięci i korekt.

Przykład:

```bash
python -m unittest discover -s odyn_ai/tests
python -m unittest discover -s nexus_core/reasoning/tests
python -m unittest discover -s nexus_core/memory/tests
```

Przed uznaniem zmiany za gotową należy uruchomić odpowiedni zestaw testów oraz sprawdzić wynik CI.

---

## Stan projektu

ODYN AI jest aktywnie rozwijanym systemem.

### Obecny fundament

- [x] Dual GGUF Engine
- [x] per-request inference parameters
- [x] Cognitive Engine
- [x] Graph of Thought
- [x] Reflexion
- [x] cognitive modulation
- [x] environmental stress z historii wykonania
- [x] bitemporal memory
- [x] experience memory
- [x] opcjonalny RAG
- [x] Coding Agent
- [x] Execution Engine
- [x] Autonomous Build Orchestrator
- [x] GitHub integration
- [x] Voice Command API
- [x] testy integracyjne warstwy poznawczej

### Rozwijane kierunki

- [ ] pełny Agents Builder UI
- [ ] pełny No-Code App Builder
- [ ] rozszerzona orkiestracja agentów
- [ ] bogatsze modele pamięci proceduralnej
- [ ] dynamiczna ocena strategii na podstawie długoterminowych wyników
- [ ] dalsza automatyzacja Android Build Pipeline
- [ ] rozszerzona obsługa modeli lokalnych

---

## Filozofia projektu

ODYN AI ma łączyć cztery warstwy:

```text
MODEL
  +
MEMORY
  +
COGNITION
  +
EXECUTION
```

Sam model generuje tekst.

ODYN AI ma dodatkowo:

- pamiętać doświadczenia,
- planować działanie,
- wybierać strategię,
- wykonywać zmiany,
- testować rezultat,
- reagować na błędy,
- korygować własne działania,
- zachowywać skuteczne procedury,
- dostosowywać inferencję do warunków wykonania.

To właśnie ta pętla stanowi podstawę autonomicznego środowiska ODYN AI.

---

## Autor / Projekt

**ODYN AI**  
Projekt: **Moje Alterego / Andrzej Mikulski**

Repository:

https://github.com/mojealterego/ODYN-AI

Branch rozwojowy:

`codex/odyn-ai`

---

## License

MIT
