# READMEODYN — dziennik techniczny ODYN AI

> Dokument roboczy projektu. Jest aktualizowany po każdym audycie i każdej wykonanej zmianie.
> Źródło kodu: `mojealterego/ODYN-AI`.

## 1. Stan bazowy audytu

**Data:** 2026-09-29  
**Gałąź bazowa:** `codex/termux-five-goals`  
**Gałąź prac ODYN:** `codex/odyn-ai`  
**PR:** #2 — `feat(odyn): add ODYN AI local-first runtime`  
**HEAD przed audytem:** `dea74d0f85c6eb19c2796e2c92199c1120edb489`

Audyt strukturalny gałęzi bazowej wykazał **6906 wpisów drzewa**, w tym **5967 plików i 939 katalogów**. Repozytorium zawiera równolegle warstwę bazowego Hermes/Android oraz nową warstwę ODYN pod `odyn_ai/`.

## 2. Zakres PR #2

PR #2 dodaje 30 plików obejmujących:

- polskojęzyczny interfejs ODYN,
- Agents Builder No Code/Code,
- App Builder Web/Android,
- formularze No Code,
- IDE/workspace,
- strumieniowanie czatu SSE,
- fasadę dwóch modeli GGUF,
- fallback Python,
- pamięć RAG,
- wyszukiwanie WWW,
- bramę MCP,
- trwały rejestr MCP,
- eksport PDF/DOCX/XLSX,
- testy jednostkowe i workflow CI.

## 3. Wyniki audytu przed poprawkami

### Krytyczne / blokujące

1. **CI był czerwony.**
   - Kompilacja `odyn_ai` przechodziła.
   - Testy nie startowały poprawnie z powodu brakujących zależności: `docx`, `httpx`, `numpy`.
   - Workflow instalował tylko `pydantic` i `pytest`, mimo że testy importują dodatkowe biblioteki.

2. **RAG wymagał importu `llama-cpp-python` już podczas importowania modułu.**
   - Utrudniało to lekkie testowanie i narzędzia, nawet gdy natywny runtime GGUF nie był potrzebny.
   - Granica zależności została przeniesiona do momentu inicjalizacji silnika.

3. **Podgląd formularzy miał niebezpieczne składanie HTML.**
   - Nazwy formularzy, etykiety, wartości domyślne i opcje trafiały do HTML bez kodowania.
   - Ten sam problem występował po stronie Python oraz w JS używającym `innerHTML`.
   - Dodano kodowanie HTML i regresję testową.

## 4. Zmiany wykonane w tej sesji

### 4.1 CI

Dodano:

`odyn_ai/requirements_test.txt`

Zawiera zależności potrzebne do uruchomienia testów bez instalowania ciężkiego `llama-cpp-python`.

Workflow:

`/.github/workflows/odyn-ai.yml`

został zmieniony tak, aby instalować właśnie ten profil testowy.

**Cel:** testy jednostkowe mają być niezależne od natywnego backendu inferencji.

### 4.2 RAG

`odyn_ai/core/rag_memory.py`

- `llama_cpp.Llama` nie jest już importowany bezwarunkowo na poziomie modułu.
- Biblioteka jest ładowana dopiero przy tworzeniu rzeczywistego embeddera.
- Istniejące mocki testowe zachowują możliwość zastąpienia tej granicy.

### 4.3 Bezpieczeństwo formularzy

`odyn_ai/core/builders.py`

- dodano kontekstowe HTML escaping danych użytkownika podczas generowania preview.

`odyn_ai/ui/app.js`

- dodano `escapeHtml()` przed dynamicznym renderowaniem preview formularza.

### 4.4 Testy

Dodano regresje dla:

- braku natywnego runtime RAG,
- kodowania danych formularza przed renderowaniem HTML.

## 5. Aktualny stan funkcjonalny

### Działa koncepcyjnie / zaimplementowane

- [x] Polish-first UI
- [x] Agents Builder: No Code
- [x] Agents Builder: Code storage bez wykonywania kodu
- [x] App Builder: Web
- [x] App Builder: Android — generator struktury projektu
- [x] No Code form model
- [x] formularze z typami pól i walidacją deklaratywną
- [x] lokalny JSON persistence
- [x] SSE chat transport
- [x] auto/server/python backend selection
- [x] llama-server speculative decoding path
- [x] Python prompt-lookup fallback
- [x] MCP HTTP gateway
- [x] persistent MCP registry
- [x] RAG memory
- [x] PDF/DOCX/XLSX generator

### Nadal wymaga dalszej implementacji

1. **Android App Builder nie jest jeszcze pełnym builderem APK.**
   Generator tworzy pliki projektu, ale obecnie nie dostarcza kompletnego Gradle Wrappera i nie wykonuje rzeczywistego buildu APK.

2. **IDE nie wykonuje jeszcze poleceń.**
   Przyciski Run/Build/Test w obecnej wersji przygotowują/wyświetlają polecenie zamiast uruchamiać proces build/test.

3. **MCP nie jest jeszcze wystawione jako pełny zestaw endpointów API.**
   Modele `mcp_api_models.py` istnieją, ale trzeba dokończyć warstwę HTTP zarządzającą serwerami i wywołaniami narzędzi.

4. **Eksport dokumentów nie jest jeszcze podłączony do API/UI.**
   Generator istnieje, ale brak kompletnego przepływu użytkownik → endpoint → plik/artefakt.

5. **RAG wymaga osobnego, świadomego zarządzania modelem embeddingowym.**
   Brak automatycznego pobierania/weryfikacji modelu.

6. **Warstwa bezpieczeństwa MCP wymaga dalszego utwardzenia.**
   Należy dodać politykę endpointów, uwierzytelnianie, kontrolę dostępu, limity oraz ochronę przed niepożądanym ruchem sieciowym.

7. **Search/Web research wymaga lepszego kontraktu źródeł.**
   Wyniki powinny mieć identyfikatory źródeł, timestamp, status i kontrolę błędów zamiast być tylko tekstem wstrzykiwanym do promptu.

8. **Persistence wymaga wersjonowania schematu.**
   Obecny JSON Store jest prosty i atomowy, ale nie ma migracji wersji danych.

## 6. Obszary do następnego audytu

### Priorytet P0

- rzeczywisty build APK,
- wykonanie Run/Build/Test w IDE,
- pełna integracja MCP API,
- testy API FastAPI,
- testy SSE,
- testy backend selection,
- testy rzeczywistego llama-server na fixture/mock binary.

### Priorytet P1

- bezpieczeństwo MCP,
- walidacja i sanitizacja workspace,
- stabilność persistence,
- obsługa błędów i time-outów,
- kontrola procesów llama-server,
- lifecycle aplikacji FastAPI.

### Priorytet P2

- jakość generatora Web,
- npm lockfile / reproducible builds,
- wersjonowanie projektów,
- import/export projektów,
- GitHub integration,
- pełny lokalny model manager,
- telemetry/diagnostics.

## 7. Zasada pracy ODYN

Każda kolejna zmiana ma być zapisana tutaj w formacie:

- **data**
- **cel**
- **zmienione pliki**
- **co zmieniono**
- **test/regresja**
- **wynik CI**
- **pozostałe ryzyka**

Nie uznajemy funkcji za zakończoną wyłącznie dlatego, że kod się kompiluje. Funkcja jest zakończona dopiero po przejściu odpowiednich testów i weryfikacji runtime.

## 8. Log zmian

### 2026-09-29 — Audyt #1 / stabilizacja fundamentu

**Zmiany:**
- dodano `odyn_ai/requirements_test.txt`,
- naprawiono instalację zależności w CI,
- przeniesiono import `llama_cpp` RAG do lazy boundary,
- dodano escaping HTML po stronie Python,
- dodano escaping HTML w preview JS,
- dodano regresje testowe.

**Weryfikacja:**
- przed zmianami: `compileall` PASS,
- przed zmianami: unittest FAIL — 4 moduły testowe nie importowały się przez brak zależności,
- pierwszy run po dodaniu zależności: 30 testów uruchomiło się; ujawniono 4 regresje testowe i 1 błąd mocka,
- skorygowano: mock async MCP, asercję workspace, asercję CSS oraz polskie etykiety UI.

**Dalsza weryfikacja:** pierwszy run po stabilizacji zależności ujawnił 5 latentnych regresji testowych; zostały skorygowane w testach/mocks oraz w widocznych etykietach UI.

**Następny krok:** kolejny run CI, a następnie audyt rzeczywistego Android/Web build pipeline oraz integracji MCP/API.

---

## 9. Referencje techniczne

- FastAPI SSE: endpoint `/chat/stream` korzysta z oficjalnego `EventSourceResponse` / `ServerSentEvent`.
- llama.cpp: ścieżka dwóch GGUF używa `--model-draft`, `--spec-type draft-simple`, `--spec-draft-n-max` oraz `-ngld`.
- llama-cpp-python: Python fallback wykorzystuje `LlamaPromptLookupDecoding`.

Ten dokument jest częścią procesu inżynierskiego ODYN i powinien być aktualizowany przy każdej kolejnej zmianie.
