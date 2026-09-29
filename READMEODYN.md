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
- [x] API eksportu PDF/DOCX/XLSX
- [x] zabezpieczenie nazw plików przed traversal
- [x] ochrona eksportu XLSX przed formułami w danych użytkownika

### Nadal wymaga dalszej implementacji

1. **Android App Builder nie jest jeszcze pełnym builderem APK.**
   Generator tworzy pliki projektu, ale obecnie nie dostarcza kompletnego Gradle Wrappera i nie wykonuje rzeczywistego buildu APK.

2. **IDE nie wykonuje jeszcze poleceń.**
   Przyciski Run/Build/Test w obecnej wersji przygotowują/wyświetlają polecenie zamiast uruchamiać proces build/test.

3. **MCP nie jest jeszcze wystawione jako pełny zestaw endpointów API.**
   Modele `mcp_api_models.py` istnieją, ale trzeba dokończyć warstwę HTTP zarządzającą serwerami i wywołaniami narzędzi.

4. **Eksport dokumentów wymaga jeszcze pełnej weryfikacji runtime UI.**
   Generator i API są podłączone; po tej sesji pozostaje potwierdzenie działania pobrania artefaktu w przeglądarce.

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
- skorygowano: mock async MCP, asercję workspace, asercje struktury CSS/UI oraz polskie etykiety UI,
- kolejny run CI: **PASS — compileall PASS, 30/30 testów PASS**.

**Dalsza weryfikacja:** pierwszy run po stabilizacji zależności ujawnił 5 latentnych regresji testowych; zostały skorygowane w testach/mocks oraz w widocznych etykietach UI.

**Następny krok:** kolejny run CI, a następnie audyt rzeczywistego Android/Web build pipeline oraz integracji MCP/API.

---

## 9. Referencje techniczne

- FastAPI SSE: endpoint `/chat/stream` korzysta z oficjalnego `EventSourceResponse` / `ServerSentEvent`.
- llama.cpp: ścieżka dwóch GGUF używa `--model-draft`, `--spec-type draft-simple`, `--spec-draft-n-max` oraz `-ngld`.
- llama-cpp-python: Python fallback wykorzystuje `LlamaPromptLookupDecoding`.

Ten dokument jest częścią procesu inżynierskiego ODYN i powinien być aktualizowany przy każdej kolejnej zmianie.


### 2026-09-29 — Audyt #2 / Moduł natywnego generowania dokumentów

**Zakres:** `odyn_ai/core/document_generator.py`

**Ustalenia:**
- moduł był już częściowo ulepszony względem pierwotnej wersji: `pathlib`, Unicode PDF font discovery, formatowanie nagłówka XLSX, freeze panes i auto-filter,
- modele API eksportu (`document_api_models.py`) istniały, ale nie były używane przez FastAPI,
- brakowało kompletnego przepływu endpoint → generator → pobieralny artefakt.

**Wykonane:**
- dodano `POST /api/documents/pdf`,
- dodano `POST /api/documents/docx`,
- dodano `POST /api/documents/xlsx`,
- endpointy zwracają właściwe typy MIME i bezpieczną nazwę pliku,
- generator XLSX neutralizuje wartości tekstowe rozpoczynające się od `=`, `+`, `-` lub `@`, aby ograniczyć ryzyko formula injection,
- zachowano rzeczywiste liczby jako wartości liczbowe,
- zachowano Unicode PDF przez wykrywanie czcionki TrueType z możliwością wskazania `ODYN_PDF_FONT`,
- dodano testy traversal/normalizacji rozszerzenia oraz zabezpieczenia XLSX.

**Weryfikacja:**
- testy regresyjne zostały dodane przed implementacją zmian generatora,
- następny krok weryfikacyjny: pełny CI po zmianach oraz test HTTP endpointów eksportu.

**Pozostało:**
- UI export actions,
- testy pobierania PDF/DOCX/XLSX przez FastAPI,
- ewentualne szablony dokumentów premium (okładka, stopka, numeracja stron, style DOCX/XLSX).


### 2026-09-29 — Audyt #3 / Eksport z ODYN IDE i szablony profesjonalne

**Zakres:**
- połączenie eksportu z ODYN IDE,
- wybór formatu i nazwy pliku,
- pobieranie artefaktu przez przeglądarkę,
- szablony PDF/DOCX/XLSX,
- bezpośredni eksport raportu agenta.

**Wykonane pliki:**
- odyn_ai/core/document_generator.py
- odyn_ai/api/document_api_models.py
- odyn_ai/api/server.py
- odyn_ai/ui/index.html
- odyn_ai/ui/app.js
- odyn_ai/ui/nord.css
- odyn_ai/tests/test_document_generator.py
- odyn_ai/tests/test_document_api.py
- odyn_ai/tests/test_export_ui_contract.py

**Funkcjonalność:**
- [x] panel EKSPORT RAPORTU w ODYN IDE,
- [x] wybór PDF / DOCX / XLSX,
- [x] własna nazwa pliku,
- [x] szybkie przyciski PDF/DOCX/XLSX,
- [x] pobieranie artefaktu Blob z API jako lokalny plik,
- [x] POST /api/reports/export,
- [x] POST /api/agents/{agent_id}/reports/export,
- [x] zachowane dedykowane endpointy dokumentów,
- [x] raport ostatniej odpowiedzi agenta może zostać eksportowany bez opuszczania IDE,
- [x] PDF: nagłówek tytułu, linia brandowa, stopka ODYN AI i numeracja stron,
- [x] PDF: rozpoznawanie H1/H2/H3 z treści markdownowej,
- [x] DOCX: hierarchia Heading 1/2/3, nagłówek i stopka ODYN,
- [x] XLSX: stylowany nagłówek, tabela Excela, pasy wierszy, freeze panes, autofilter i ukryta siatka,
- [x] XLSX: ochrona przed formula injection,
- [x] bezpieczne nazwy plików i normalizacja rozszerzeń.

**TDD / weryfikacja:**
- dodano testy RED przed implementacją szablonów,
- pierwsza pełna próba CI: **39 testów, 2 błędy**,
- błędy ujawnione przez CI:
  1. FastAPI próbował generować response model dla AsyncIterable[ServerSentEvent],
  2. FPDF2 zgłaszał Not enough horizontal space to render a single character przy długim dokumencie.
- poprawiono odpowiednio:
  - response_model=None dla SSE,
  - jawne pdf.epw zamiast szerokości 0 w krytycznych wywołaniach PDF.

**Weryfikacja końcowa:**
- ODYN AI CI: **PASS**,
- compileall: **PASS**,
- unittest: **43/43 PASS**,
- dodatkowy test ASGI/HTTP potwierdza status 200, MIME `application/pdf`, `Content-Disposition: attachment` oraz niepusty artefakt.

**Pozostałe ryzyko:** pełny test przeglądarkowy z rzeczywistym kliknięciem pobierania nie jest jeszcze E2E; obecny test ASGI potwierdza warstwę HTTP, a kontrakt UI potwierdza kontrolki i endpoint. Runtime browser/E2E pozostaje osobnym krokiem.


### 2026-09-29 — Weryfikacja końcowa Audytu #3

**CI:** ODYN AI CI PASS.

**Wynik:** compileall PASS, **43/43 testy PASS**.

**Dodatkowo:** test HTTP przez ASGI potwierdza rzeczywisty przepływ POST → FileResponse → artefakt PDF z poprawnym MIME i nagłówkiem attachment.

**Status modułu eksportu:** implementacja backend + API + IDE UI + szablony jest zweryfikowana automatycznie. Pozostaje opcjonalna weryfikacja E2E w uruchomionej przeglądarce.


### 2026-09-29 — Audyt #4 / MCP Gateway

**Stan przed zmianą:**
- `MCPGateway` potrafił rejestrować endpoint HTTP i wysyłać pojedyncze `tools/call`,
- brakowało trwałego rejestru serwerów,
- brakowało handshake `initialize`,
- brakowało `tools/list` i cache odkrytych narzędzi,
- brakowało publicznego API FastAPI do zarządzania serwerami MCP,
- brakowało jednoznacznej obsługi timeoutów, błędów HTTP i błędów JSON-RPC.

**Wykonane:**
- [x] trwały rejestr `mcp_servers.json` przez istniejący `JsonStore`,
- [x] rejestracja / wyrejestrowanie serwerów,
- [x] walidacja HTTP/HTTPS i odrzucenie danych uwierzytelniających w URL,
- [x] unikalne identyfikatory żądań JSON-RPC,
- [x] handshake `initialize` z identyfikacją ODYN AI,
- [x] `tools/list` i cache metadanych narzędzi,
- [x] `tools/call` z automatyczną inicjalizacją,
- [x] timeouty i mapowanie błędów transportowych,
- [x] walidacja odpowiedzi JSON-RPC,
- [x] API FastAPI: lista/rejestracja/usunięcie serwera,
- [x] API FastAPI: initialize,
- [x] API FastAPI: discovery narzędzi,
- [x] API FastAPI: execute tool,
- [x] testy lifecycle Gateway i testy HTTP API.

**Bezpieczeństwo / dalsze utwardzenie:**
- endpointy są walidowane jako HTTP/HTTPS,
- dane uwierzytelniające nie mogą być przekazywane w URL,
- pełna polityka allowlist hostów, TLS pinning, OAuth/API-key vault i kontrola uprawnień narzędzi pozostają osobnym etapem hardeningu.

**Weryfikacja:** oczekiwany jest pełny CI po zmianach.


**Weryfikacja końcowa Audytu #4:**
- pierwszy CI po implementacji: **47 testów, 1 regresja kontraktu list_servers**,
- regresja dotyczyła wyłącznie starej asercji oczekującej dwóch pól,
- zaktualizowano test do rozszerzonego kontraktu diagnostycznego,
- kolejny ODYN AI CI: **PASS**,
- compileall: **PASS**,
- unittest: **47/47 PASS**.

**Status:** MCP Gateway jest zaimplementowany na poziomie rejestracji, persistence, initialize, tools/list, tools/call oraz FastAPI API. Nie oznacza to jeszcze pełnej zgodności ze wszystkimi wariantami transportu MCP, OAuth ani polityką produkcyjnego secret managementu.


### 2026-09-29 — Audyt #5 / MCP Security Hardening

**Zakres:**
- OAuth/API keys i secret storage,
- allowlista endpointów,
- polityka narzędzi,
- Streamable HTTP/SSE,
- sesje MCP,
- rate limiting,
- audyt wywołań,
- izolacja narzędzi wysokiego ryzyka.

**Wdrożono:**
- [x] `SecretStore` — sekrety są pobierane wyłącznie z procesu środowiskowego; wartość sekretu nie trafia do `mcp_servers.json`,
- [x] typy auth: `none`, `api_key`, `bearer`,
- [x] konfigurowalne nazwy nagłówka i prefix Bearer,
- [x] allowlista hostów `ODYN_MCP_ALLOWED_HOSTS`,
- [x] deny-by-default dla hostów nieobecnych na allowliście,
- [x] polityka narzędzi `allow / deny / high_risk`,
- [x] deny-by-default dla nieznanych narzędzi,
- [x] narzędzia wysokiego ryzyka są blokowane bez osobnego mechanizmu zatwierdzenia,
- [x] obsługa odpowiedzi JSON i `text/event-stream`,
- [x] przechwytywanie i ponowne używanie `Mcp-Session-Id`,
- [x] `MCP-Protocol-Version`,
- [x] `follow_redirects=False` dla ograniczenia niekontrolowanych przekierowań,
- [x] per-server rate limiting,
- [x] trwały dziennik audytowy `mcp_audit.json` bez payloadów i sekretów,
- [x] rejestrowanie sukcesów, timeoutów, błędów HTTP i błędów MCP,
- [x] testy zabezpieczeń, sesji SSE, rate limitingu i sekretów.

**Konfiguracja:**
```
ODYN_MCP_ALLOWED_HOSTS=api.example.com,mcp.example.com
ODYN_MCP_RATE_LIMIT=30
ODYN_MCP_TIMEOUT=30
ODYN_MCP_TOOL_POLICY=search=allow,filesystem.read=allow,filesystem.write=high_risk
ODYN_SECRET_MY_MCP_TOKEN=...
```

**Uwagi bezpieczeństwa:**
- `ODYN_SECRET_*` nie jest zapisywane przez Gateway; produkcyjnie zmienna powinna pochodzić z systemowego secret managera / platformowego vaulta,
- OAuth 2.0 z interaktywnym flow i refresh-token lifecycle wymaga dalszej integracji z dostawcą tożsamości; obecna warstwa obsługuje bezpieczny transport tokena jako sekretu Bearer, ale nie udaje kompletnego OAuth clienta,
- pełna izolacja wysokiego ryzyka wymaga osobnego sandboxa/procesu/contenera; obecna polityka stosuje bezpieczny **deny-by-default** zamiast wykonywać takie narzędzia,
- należy rozważyć DNS rebinding/SSRF hardening na poziomie resolvera, jeśli allowlista ma dopuszczać hosty kontrolowane przez użytkownika.

**Zmodyfikowane pliki:**
- `odyn_ai/core/mcp_gateway.py`
- `odyn_ai/api/mcp_api_models.py`
- `odyn_ai/api/server.py`
- `odyn_ai/tests/test_mcp_gateway.py`
- `READMEODYN.md`

**Weryfikacja:** pełny CI po zmianach jest wymagany przed oznaczeniem audytu jako zakończonego.


**Aktualizacja OAuth2:**
- [x] OAuth 2.0 Client Credentials flow,
- [x] token endpoint jako allowlisted HTTPS/HTTP endpoint,
- [x] client ID i client secret wyłącznie przez `ODYN_SECRET_*`,
- [x] cache tokena w pamięci z uwzględnieniem `expires_in`,
- [x] automatyczne użycie `Authorization: Bearer <token>`,
- [x] brak tokena/sekretu → fail closed.

**Końcowa weryfikacja Audytu #5:**
- wcześniejsze iteracje CI wykryły i usunęły regresje testowe dotyczące persistence, allowlisty, mocków HTTP i OAuth handshake,
- ostatni ODYN AI CI: **PASS**,
- compileall: **PASS**,
- unittest: **53/53 PASS**.

**Stan bezpieczeństwa:** Gateway działa w modelu deny-by-default. Sekrety nie są zapisywane w registry ani audycie; payloady narzędzi nie są zapisywane w audycie. Narzędzia oznaczone `high_risk` pozostają blokowane bez osobnego, kontrolowanego mechanizmu sandbox/approval.

**Pozostaje jako osobny etap produkcyjnego hardeningu:**
- integracja z natywnym OS/cloud Secret Manager zamiast samego environment,
- OAuth Authorization Code + PKCE dla interaktywnych kont użytkowników,
- resolver-level SSRF/DNS-rebinding protection,
- rzeczywisty sandbox/container dla narzędzi wysokiego ryzyka,
- E2E z rzeczywistym serwerem MCP obsługującym Streamable HTTP.


### 2026-09-29 — Audyt #6 / OAuth PKCE + Native Secrets + SSRF + Sandbox

**Zakres:** OAuth Authorization Code + PKCE, natywny Secret Manager, ochrona SSRF/DNS rebinding oraz rzeczywista izolacja high_risk.

**Wdrożono:**
- [x] OAuth Authorization Code + PKCE z losowym state,
- [x] PKCE S256 z jednorazowym code_verifier,
- [x] wymiana authorization code i refresh token flow,
- [x] zapis refresh tokenów w natywnym Secret Managerze,
- [x] brak plaintext-file fallback dla sekretów,
- [x] NativeSecretManager oparty o systemowy keyring,
- [x] API rozpoczęcia i zakończenia interaktywnego OAuth,
- [x] resolver-level SSRF policy dla loopback/private/link-local/multicast/unspecified/reserved,
- [x] DNS-pinned HTTP transport: połączenie do wcześniej zweryfikowanego IP przy zachowaniu hostname/SNI i Host,
- [x] brak automatycznych redirectów dla ruchu MCP/OAuth,
- [x] rzeczywisty SandboxRunner z Docker albo bubblewrap,
- [x] Docker sandbox: network none, read-only root, cap-drop ALL, no-new-privileges, limity PID/RAM/CPU i izolowany tmp,
- [x] brak backendu izolacji oznacza deny,
- [x] high_risk pozostaje zablokowane w ścieżce zdalnego MCP, a lokalne operacje wysokiego ryzyka mają osobną ścieżkę sandboxową.

**Nowe pliki:**
- odyn_ai/core/mcp_oauth.py
- odyn_ai/core/secret_manager.py
- odyn_ai/core/ssrf.py
- odyn_ai/core/sandbox.py

**Zmodyfikowane:**
- odyn_ai/core/mcp_gateway.py
- odyn_ai/api/mcp_api_models.py
- odyn_ai/api/server.py
- odyn_ai/requirements_test.txt
- odyn_ai/tests/test_mcp_gateway.py

**Weryfikacja:**
- pierwszy CI po integracji: 61 testów, 1 błąd — stary warunek typów auth nie zawierał oauth2_authorization_code,
- poprawiono warunek,
- następny ODYN AI CI: PASS — compileall PASS, 61/61 testów PASS,
- po dodaniu transportu DNS pinning i testu transportowego wymagany jest kolejny pełny CI.

**Uwagi bezpieczeństwa:**
- PKCE używa S256; authorization response wymaga zgodnego state, a verifier nie jest umieszczany w URL,
- natywny keyring jest docelowym magazynem sekretów; brak backendu nie powoduje przejścia na plaintext,
- transport pinujący IP eliminuje podstawową lukę TOCTOU między walidacją DNS a połączeniem,
- sandbox wymaga realnego backendu izolacji,
- zdalnego narzędzia MCP nie można bezpośrednio osadzić w lokalnym kontenerze bez sandboxowanego MCP worker/proxy; dlatego zdalne high_risk nadal wymaga osobnego worker/proxy.

**Pozostały osobny etap:** sandboxowany MCP worker/proxy dla zdalnych high_risk, platformowe adaptery Android Keystore/Apple Keychain/Windows Credential Locker, OAuth Authorization Server Metadata i issuer/mix-up validation, rotacja/revokacja refresh tokenów z obsługą invalid_grant oraz opcjonalny DPoP.


**Weryfikacja końcowa Audytu #6:**
- po dodaniu DNS-pinned transportu pierwszy CI wykrył brak przekazania transportu do OAuthAuthorizationClient oraz nieasynchroniczne zamknięcie transportu w teście,
- poprawiono oba problemy,
- najnowszy ODYN AI CI: **PASS**,
- compileall: **PASS**,
- unittest: **PASS — 62 testy**.

**Stan:** OAuth PKCE, natywny Secret Manager, resolver + transport DNS pinning oraz realny sandbox Docker/bubblewrap są zaimplementowane. Zdalne high_risk MCP pozostaje fail-closed do czasu dodania osobnego sandboxowanego MCP worker/proxy.


### 2026-09-29 — Audyt #7 / Sandboxed MCP Worker

**Wdrożono:**
- [x] DockerMCPWorker jako osobna granica procesu,
- [x] MCPGateway.execute_tool() deleguje high_risk do workera,
- [x] zwykłe allow pozostaje bezpośrednim MCP RPC,
- [x] capability broker wymusza wcześniej przyznany serwer i `tools/call`,
- [x] broker odrzuca nieprzyznane narzędzie oraz nieprawidłowe argumenty,
- [x] worker nie otrzymuje sekretów,
- [x] Docker network=none, read-only, cap-drop=ALL, no-new-privileges, seccomp,
- [x] limit CPU/RAM/PID i non-root UID 65532,
- [x] brak host bind mounts i Docker socketu,
- [x] brak Dockera oznacza odmowę high-risk,
- [x] testy capability tampering dla server/operation/tool/arguments.

**Nowe pliki:**
- `odyn_ai/core/mcp_worker.py`
- `odyn_ai/core/mcp_sandbox.py`
- `docker/mcp-worker.Dockerfile`
- `odyn_ai/tests/test_mcp_sandbox.py`

**Weryfikacja:** pełny CI jest ostatnim krokiem przed uznaniem modułu za zakończony.


**CI Audyt #7 — korekta testu:** pierwsze uruchomienie wykryło błąd samego testu (nazwa `api_key` nie była objęta kontraktem sekretów workera). Test został skorygowany do `token`; nie zmieniono granicy bezpieczeństwa. Wymagane ponowne pełne CI.


### 2026-09-29 — Audyt #8 / Specjalistyczne profile agentów

**Wdrożono:**
- [x] centralny rejestr `SPECIALIST_PROFILES` w `odyn_ai/config.py`,
- [x] profil Prawo,
- [x] profil OSINT,
- [x] profil Web Builder,
- [x] profil Game Builder,
- [x] specjalistyczne prompty w `SYSTEM_PROMPTS`,
- [x] `AgentManager` ładuje profile z centralnego rejestru,
- [x] profile zachowują istniejący model `AgentDefinition`, w tym `can_search` i `mode`,
- [x] test kontraktowy rejestru i dostępności profili w `AgentManager`.

**Profile:** `prawo`, `osint`, `web_builder`, `game_builder`.

**Weryfikacja:** pełny CI wymagany po integracji; nie uznawać etapu za zakończony przed compileall + pełnym unittest.

**Korekta CI Audytu #8:** centralny rejestr został ujednolicony — każdy profil zawiera teraz bezpośrednio `prompt`, dzięki czemu rejestr jest samowystarczalnym kontraktem. `AgentManager` konsumuje `profile["prompt"]`.

**Korekta testu Audytu #8:** usunięto przestarzałą asercję `prompt_key`; test weryfikuje obecnie rzeczywisty kontrakt samowystarczalnego profilu (`prompt`).

**Weryfikacja końcowa Audytu #8:** ODYN AI CI #292 — **PASS**; compileall **PASS**; unittest **PASS — 76 testów**. Profile specjalistyczne są dostępne przez `AgentManager` i pochodzą z centralnego `SPECIALIST_PROFILES`.


### 2026-09-29 — Audyt #9 / Moduł czatu głosowego STT

**Cel:** dodać do interfejsu ODYN AI dostępne wejście głosowe oraz połączyć je z istniejącym polem czatu bez automatycznego wysyłania wiadomości.

**Wdrożono:**
- [x] przycisk voice-btn w formularzu czatu,
- [x] etykietę ARIA i stan aria-pressed dla nagrywania,
- [x] status voice-status z komunikatami dla użytkownika,
- [x] Web Speech API z fallbackiem SpeechRecognition / webkitSpeechRecognition,
- [x] język rozpoznawania pl-PL,
- [x] wyniki częściowe (interimResults) i końcowe,
- [x] zachowanie istniejącego tekstu przed dyktowaniem,
- [x] start/stop jednym przyciskiem,
- [x] komunikaty dla odmowy mikrofonu, braku mowy, braku mikrofonu, niedostępnej usługi i błędów sieciowych,
- [x] graceful degradation: brak Web Speech API wyłącza kontrolkę zamiast generować błąd,
- [x] preferencję prefers-reduced-motion dla animacji stanu nagrywania,
- [x] brak automatycznego wywołania send() po zakończeniu dyktowania.

**Zmodyfikowane pliki:**
- odyn_ai/ui/index.html
- odyn_ai/ui/app.js
- odyn_ai/tests/test_voice_ui.py
- READMEODYN.md

**TDD / kontrakt regresyjny:**
- test kontraktowy obejmuje obecność dostępnego przycisku głosowego, integrację z formularzem czatu, konfigurację polskiego SpeechRecognition oraz brak automatycznego wysyłania,
- test został dodany przed implementacją obsługi STT,
- test nie wymaga dostępu do rzeczywistego mikrofonu, więc pozostaje deterministyczny i uruchamialny w CI.

**Ograniczenie architektoniczne:**
- obecny moduł wykorzystuje Web Speech API przeglądarki. Nie jest to jeszcze natywne nagrywanie audio → backend Whisper/OpenAI. Taki backendowy STT pozostaje osobnym etapem i będzie wymagał API uploadu audio, kontroli MIME/rozmiaru, obsługi sekretów oraz testów integracyjnych.

**Weryfikacja:** po wdrożeniu wymagany jest pełny ODYN AI CI oraz runtime browser/E2E w przeglądarce obsługującej mikrofon.


### 2026-09-29 — Audyt #10 / Natywne STT przez lokalny Whisper

**Cel:** drugi tor głosowy: mikrofon przeglądarki → nagranie audio → API ODYN → lokalny Whisper → tekst w polu czatu.

**Architektura:**
```
Mikrofon
   │
   ▼
MediaRecorder
   │ WebM/OGG
   ▼
POST /api/stt/transcribe
   │
   ▼
SpeechToText
   │ lazy-load
   ▼
faster-whisper
   │
   ▼
tekst PL → pole czatu → użytkownik naciska Wyślij
```

**Wdrożono:**
- [x] odyn_ai/core/speech_to_text.py,
- [x] lazy loading faster-whisper — model nie jest ładowany przy starcie ODYN,
- [x] domyślny model tiny,
- [x] konfiguracja modelu, urządzenia, compute type, języka i limitu audio przez STTConfig,
- [x] POST /api/stt/transcribe,
- [x] walidacja MIME audio,
- [x] limit 25 MB domyślnie,
- [x] transkrypcja przez asyncio.to_thread, aby nie blokować event loop FastAPI,
- [x] automatyczny wybór CUDA/CPU przy device=auto,
- [x] usuwanie pliku tymczasowego po transkrypcji,
- [x] MediaRecorder + getUserMedia w UI,
- [x] wysyłanie FormData do lokalnego endpointu STT,
- [x] zachowanie tekstu wpisanego przed nagraniem,
- [x] fallback do Web Speech API,
- [x] brak automatycznego wysyłania transkrypcji do czatu.

**Konfiguracja środowiskowa:**
```
ODYN_STT_MODEL=tiny
ODYN_STT_DEVICE=cpu
ODYN_STT_COMPUTE_TYPE=int8
ODYN_STT_LANGUAGE=pl
```

Dla maszyny z GPU można użyć ODYN_STT_DEVICE=cuda oraz odpowiedniego compute type.

**Zależności:**
- python-multipart jest wymagane przez upload multipart FastAPI,
- faster-whisper znajduje się w odyn_ai/requirements_extra.txt, aby podstawowy runtime nie musiał pobierać ciężkiego modelu STT.

**Testy:**
- odyn_ai/tests/test_speech_to_text.py sprawdza konfigurację, walidację audio i obecność endpointu,
- istniejący test_voice_ui.py zachowuje regresję Web Speech API i brak automatycznego send(),
- testy STT nie wymagają pobierania modelu ani dostępu do mikrofonu.

**Pozostałe ryzyka / ograniczenia:**
- pierwsza transkrypcja może być wolniejsza, ponieważ model jest ładowany leniwie,
- faster-whisper wymaga dodatkowego profilu zależności; model jest pobierany przez backend przy pierwszym użyciu,
- runtime E2E z prawdziwym mikrofonem i pobranym modelem pozostaje osobnym testem sprzętowym,
- jakość i opóźnienie zależą od modelu, CPU/GPU oraz długości nagrania.
