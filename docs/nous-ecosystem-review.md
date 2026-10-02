# Analiza ekosystemu NousResearch dla ODYN-AI

Data przeglądu: 2026-10-02. Zakres: wszystkie 30 repozytoriów wskazanych przez właściciela projektu. Odnośniki w tabeli prowadzą do sprawdzonych commitów, a nie zmiennej gałęzi `main`. [Dokładne rewizje i sprawdzone pliki](nous-ecosystem-sources.json) zawierają także identyfikatory blobów.

## Wniosek i ograniczenia przeglądu

Największą bezpośrednią wartość dają poprawki istniejącego rdzenia i lokalnej pamięci, odczyt historii bez zapisu oraz mierzenie skuteczności narzędzi. Włączanie wielu usług pamięci jednocześnie nie jest uzasadnione: obecny `MemoryManager` obsługuje pamięć wbudowaną plus najwyżej jednego zewnętrznego dostawcę. Osiem podanych repozytoriów pamięci jest wydzielonymi kopiami modułów już obecnych w tym forku. Ich README opisują przekazanie utrzymania lub poszukiwanie opiekuna; właściciel organizacji GitHub nie oznacza, że każdy moduł jest dalej aktywnie utrzymywany przez Nous.

Przegląd obejmuje drzewa plików, README, licencje, manifesty, zależności oraz wybrane punkty integracji. Nie wykonano pełnych zestawów testów 30 projektów, wywołań płatnych API, logowania do usług ani treningu modeli. Oceny przydatności dla telefonu są oceną architektury i zależności, nie pomiarem na Samsungu S24 Ultra.

Termux i Python wbudowany w APK to różne środowiska. W obecnym forku `discover_plugins()` celowo pomija dynamiczne dodatki w osadzonym Androidzie, a zewnętrzna pamięć jest pomijana dla jego `api_server`. Poprawka modułu Python nie dowodzi więc, że ten moduł jest uruchomiony w APK. Ścieżka dla Androida wymaga osobnych adapterów, pakowania i testów na urządzeniu.

## Ocena wszystkich repozytoriów

Priorytety: **P0** — poprawność i podstawy; **P1** — audyt i pomiary; **P2** — opcjonalne rozszerzenia; **P3** — zdalne aplikacje lub trening. Odroczenie UI wynika z kolejności wskazanej przez właściciela: funkcje i testy, następnie nazwa ODYN AI, UI i polska lokalizacja.

| Repozytorium / sprawdzony commit | Przydatna funkcja | Licencja w źródłach | Decyzja i warunki integracji |
|---|---|---|---|
| [hermes-agent](https://github.com/NousResearch/hermes-agent/tree/50a6abca7cff83afb0ebfe930a77c67311aa1044) | Rdzeń agenta, dostawcy modeli, MCP, pamięć i narzędzia. | MIT | P0: przenosić wybrane poprawki z testami. Historia mocno rozeszła się z forkiem; pełne zastąpienie kodu grozi utratą zmian Androida. |
| [hermes-plugin-holographic](https://github.com/NousResearch/hermes-plugin-holographic/tree/062762ab1e67dd2eeb5500dfd38785b93cb9b0e8) | Lokalne fakty SQLite/FTS5, encje, oceny zaufania; NumPy opcjonalnie. | MIT | P0: już w repo. Wdrożone poprawki konfiguracji profili, wyłączenia ekstrakcji i zamykania bazy. Termux możliwy; APK wymaga osobnej kwalifikacji. |
| [hermes-plugin-byterover](https://github.com/NousResearch/hermes-plugin-byterover/tree/1dadb1865441c5a67e94eed3ad420112dc12fdef) | Hierarchiczne notatki przez zewnętrzny CLI `brv`. | MIT | P2: już w repo. Opcjonalny dostawca; zweryfikować CLI na Android/ARM64, katalog profilu i błędy procesu. |
| [hermes-plugin-retaindb](https://github.com/NousResearch/hermes-plugin-retaindb/tree/67059eaf3c6c5696ad1cb44cd0f67c844257ae6f) | Pamięć HTTP z wyszukiwaniem hybrydowym i kategoriami. | MIT | P2: już w repo. Wymaga konta, klucza i sieci; aktywować wyłącznie jako wybrany backend. |
| [hermes-nvidia](https://github.com/NousResearch/hermes-nvidia/tree/e35b7429532c3e3fb7b4d9fea9c18e2c14740afa) | MCP dla NVIDIA App i NVIDIA Broadcast; oddzielne dodatki w podkatalogach. | Brak pliku LICENSE | P3: backend Windows z działającą aplikacją. Potrzebuje obsługi portable plugins, podkatalogów i wykrywania aplikacji; telefon może być klientem zdalnego hosta. |
| [hermes-plugin-blender](https://github.com/NousResearch/hermes-plugin-blender/tree/8aab816ce6577eb792a256b51777cbb4cd6523f0) | Sterowanie sceną przez przypięty Blender Lab MCP. | MIT wrapper; GPL-3.0-or-later serwer | P3: Blender na innym hoście; format `plugin.json`, uv i wykrywanie aplikacji. Nie kopiować serwera do APK. |
| [hermes-plugin-claude-subscription-directsdk](https://github.com/NousResearch/hermes-plugin-claude-subscription-directsdk/tree/ef73726cfaf2fa0ee041e55572f406e2c24fed83) | Eksperymentalny model przez oficjalny Claude Code CLI i relay jednego żądania. | MIT | P2: wymaga Hermes ≥0.21.4, nowego kontraktu dostawcy i zalogowanego CLI. Obecne `ProviderProfile` nie ma jego fabryki `create_client`; nie aktywować w ciemno. |
| [misaki](https://github.com/NousResearch/misaki/tree/f03fd2be7346952a83d3d4845c217fc7667f322d) | Konwersja tekstu do fonemów dla syntezy mowy, m.in. Kokoro. | Apache-2.0 | P3: komponent G2P, nie kompletny silnik TTS. eSpeakG2P przyjmuje język, ale polski głos, modele i biblioteki Android wymagają osobnych testów. |
| [hermes-plugin-supermemory](https://github.com/NousResearch/hermes-plugin-supermemory/tree/d798057e93c85198121cfd6ebf70a529559d38e6) | Pamięć semantyczna, przechwytywanie tur i konfiguracja serwera własnego lub chmurowego. | MIT | P2: już w repo. Porównać obsługę endpointu, ponownych zapisów i separacji kontenerów; testy usługi dopiero z wybranym kontem. |
| [hermes-plugin-openviking](https://github.com/NousResearch/hermes-plugin-openviking/tree/5dca75f4d3dcef9467ce2ff32e170d84c679de5f) | Wiedza w hierarchii `viking://`, ekstrakcja, zasoby i wyszukiwanie. | MIT | P2: już w repo. Dla telefonu preferować klienta istniejącego serwera. Sprawdzić tożsamość użytkownika, stan asynchronicznego zapisu i wąskie usuwanie plików pamięci. |
| [hermes-plugin-mem0](https://github.com/NousResearch/hermes-plugin-mem0/tree/3fc36950b2b7c19cdd81c6de99f10d2cbed850af) | Platforma, samodzielny serwer HTTP albo lokalny SDK/LLM/vector store. | MIT | P2: już w repo. Tryb HTTP jest lżejszym kandydatem dla telefonu; nie instalować domyślnie ciężkiego wektorowego stosu OSS. |
| [hermes-plugin-honcho](https://github.com/NousResearch/hermes-plugin-honcho/tree/32dfd0ba62ae0e8dad82d55fc81515e8c4a181a9) | Modele użytkownika, kontekst, dialektyka, OAuth i sesje. | MIT | P2: już w repo. Kontynuować poprawki izolacji użytkownika/profilu. Poprawka rozdzielenia konfiguracji peer i użytkownika gateway została już scalona. |
| [hermes-plugin-hindsight](https://github.com/NousResearch/hermes-plugin-hindsight/tree/7385025e90e98b0a4f8042f40ec956b71cb18287) | Graf pamięci, retain/recall/reflect; cloud, external lub embedded. | MIT | P2: już w repo. HTTP do usługi zewnętrznej; tryb embedded uruchamia dodatkową bazę/daemon i nie ma tu kwalifikacji Androida. |
| [Gym](https://github.com/NousResearch/Gym/tree/2d538be189de0e21c21b85af05acf7646b1b092f) | Środowiska oceny/RL i adapter wywołujący rzeczywisty `AIAgent`. | Apache-2.0 | P1 dla ocen; P3 dla treningu. Python ≥3.12 i oddzielne środowisko. Sama biblioteka nie wymaga GPU; adapter treningowy ma dodatkowe wymagania tokenów i próbkowania. |
| [hermes-memory-wiki](https://github.com/NousResearch/hermes-memory-wiki/tree/9bc3913b8474eaf4d7eec32e97af4d77957c36df) | Deterministyczny audyt historii i `MEMORY.md`/`USER.md`, bez wywołań LLM. | MIT | P1: brakowało `SessionDB(..., read_only=True)` — API dodane. Dashboard/SDK/auth/profile i przypadki błędów nadal wymagają osobnej kwalifikacji; UI odroczone. |
| [hermes-plugin-snyk](https://github.com/NousResearch/hermes-plugin-snyk/tree/2a41a07f81e45125bf82a19af1b13396ace4b81f) | Oficjalny Snyk CLI/MCP: kod, zależności, kontenery i IaC. | MIT | P2: dodatek opcjonalny. `plugin.json`, Node/npx i logowanie Snyk; nie uruchomiono skanowania ani procesu autoryzacji. |
| [hermes-plugin-touchdesigner](https://github.com/NousResearch/hermes-plugin-touchdesigner/tree/88a7a7884e5eda33cfe4b1dd5e69df7cb15d5898) | MCP do żywej sesji TouchDesigner i narzędzi kreatywnych. | MIT | P3: Windows/macOS, aplikacja i serwer HTTP; plugin ma nazwę manifestu `td`. Funkcje Python wymagają świadomie wybranego zdalnego środowiska. |
| [hermes-desktop-accent-picker](https://github.com/NousResearch/hermes-desktop-accent-picker/tree/78ef873cddcac876c8a1d12e8a8653befa0646ab) | Koło kolorów OKLCH w SDK Hermes Desktop. | MIT | Odroczone: dotyczy Desktop UI, kolor jest stanem tymczasowym. Nie jest dodatkiem Python ani elementem funkcjonalnego backendu telefonu. |
| [Automodel](https://github.com/NousResearch/Automodel/tree/922e6b0b34e3f22c6e959405d93a6aff530fc8ab) | NeMo: fine-tuning, LoRA, rozproszone modele i trening drafterów. | Apache-2.0 | P3: oddzielny pipeline treningowy, PyTorch i odpowiedni sprzęt. Nie stanowi silnika inference APK; nie dowodzi przyspieszenia lokalnego modelu. |
| [hermes-plugin-backsearch](https://github.com/NousResearch/hermes-plugin-backsearch/tree/477d81446c856a39021c069a88a047e9c89fbba3) | Wyszukiwanie/fetch archiwum według daty z ograniczeniem wycieku przyszłych danych. | MIT | P2: natywny opcjonalny plugin z `OPENREWARD_API_KEY`; `as_of` ogranicza datę crawlowania, nie deklarowaną datę publikacji. Wymaga sprawdzenia endpointu i zakresu korpusu. |
| [hermes-plugin-sprites](https://github.com/NousResearch/hermes-plugin-sprites/tree/a4881e07385beff6b440b5338dec7a415d5f1be5) | Trwałe zdalne środowisko terminala, checkpoint/restore i profile. | MIT zadeklarowana w README; brak LICENSE | P2 po rozbudowie frameworku. Brakuje `TerminalEnvironmentProvider` i rejestracji backendów. SDK/token i osobny test usługi; nie kopiować teraz kodu bez wyjaśnienia licencji. |
| [Hermes-Bot-Mode](https://github.com/NousResearch/Hermes-Bot-Mode/tree/80fee22582b871b9765a65e2992b8b5a8211c9f8) | Profile jako boty, rutyny i rozmowy w interfejsie Desktop. | MIT | Odroczone: repo zarchiwizowane, funkcja przeniesiona do `hermes-agent/apps/desktop`. Korzystać z aktualnego kodu po etapie backendu, nie z starej kopii pluginu. |
| [hermes-telegram-business](https://github.com/NousResearch/hermes-telegram-business/tree/98c60afc00d36c885bb040ebe973b1aa908886c0) | Sekretarz: szkice odpowiedzi, debounce, Send/Edit/Discard i kontrola właściciela. | MIT | P2: subskrypcja Telegram Business, bot i nowe `register_telegram_handler`. Hooku nie ma w forku. Zachować ręczne zatwierdzanie każdej odpowiedzi; nie włączać automatycznego wysyłania. |
| [image-size](https://github.com/NousResearch/image-size/tree/e6dbb45e44b82eedbb81d150a31e4850dcb500d7) | Odczyt wymiarów obrazów z nagłówków, biblioteka TypeScript/Node. | MIT | P2/P3: wykorzystać tam, gdzie działa Node. Dla Pythona/Androida sprawdzić obecne biblioteki metadanych; nie dodawać Node tylko do wymiarów obrazka. |
| [NemoClaw](https://github.com/NousResearch/NemoClaw/tree/59107b0e7b1f2f2a5ece0a7d9fb853e83d36d6c4) | OpenShell, polityki sieci/secrets, broker narzędzi; repo zawiera też adapter Hermes. | Apache-2.0 | P2/P3: zdalna infrastruktura z kontenerami. Analizować `agents/hermes`, nie tylko główny quickstart OpenClaw. Nie zastępować runtime Hermesa innym agentem. |
| [hermes-toolperf-evals](https://github.com/NousResearch/hermes-toolperf-evals/tree/4e13ec24fafe94f48c9d96f4bdadb6b5577ebc02) | Powtarzalne A/B: błędy narzędzi, sukces zadania, tury, tokeny i czas. | Brak pliku LICENSE | P1: wzorzec metodologii oraz źródło przypadków regresji. Nie przyjmować procentów z README jako wyniku ODYN-AI; późniejszy rerun nie odtwarza wcześniejszych deklaracji szybkości. |
| [RL](https://github.com/NousResearch/RL/tree/3069f2817e3000918f2665441287b3d1b7c39938) | NeMo: GRPO i inne metody post-training, Ray i wykonanie rozproszone. | Apache-2.0 | P3: trening w osobnym środowisku z odpowiednim sprzętem; domyślne zależności obejmują PyTorch/Ray. Nie włączać do bazowej instalacji telefonu. |
| [hermes-e2e-evidence](https://github.com/NousResearch/hermes-e2e-evidence/tree/65d9ce29294458f59265288ad5e4faf84a9c46d6) | Publikacja dowodów wizualnych z CI. | Brak pliku LICENSE | P1 jako sposób dokumentowania testów. Przeglądany commit gałęzi głównej zawiera tylko README; nie jest modułem wykonawczym. |
| [vllm](https://github.com/NousResearch/vllm/tree/81ef3e6a0f7651a97e480d6e340ef809160c801a) | Serwowanie modeli: batching/cache, tool parser Hermes i API zgodne z OpenAI. | Apache-2.0 | P2: użyć istniejącej obsługi własnego endpointu Hermesa do zdalnego serwera. Optymalizacje serwera nie oznaczają automatycznie wsparcia GPU/NPU telefonu. |
| [harbor-fork](https://github.com/NousResearch/harbor-fork/tree/60d4374d38c669162d18eb6deb0c6a982469f3c2) | Benchmarki izolowanych zadań, środowiska i adapter Hermes CLI. | Apache-2.0 | P1: zewnętrzna kwalifikacja agenta w izolowanych środowiskach. Python ≥3.12, kontenery albo usługa; nie uruchamiać we wspólnym katalogu pracy użytkownika. |

Brak pliku LICENSE jest ustaleniem o sprawdzonym drzewie, nie potwierdzeniem warunków redystrybucji. Manifest lub README może deklarować licencję, jednak przed kopiowaniem takiego kodu trzeba wyjaśnić zakres deklaracji. W tej partii nie skopiowano kodu repozytoriów bez pliku licencji. Wrapper Blendera i zewnętrzny serwer mają różne licencje i pozostają oddzielnymi komponentami.

## Poprawki wdrożone po analizie

### Lokalna pamięć Holographic

W istniejącym `plugins/memory/holographic` zmieniono trzy zachowania znalezione również w aktualnym wydzielonym dostawcy:

- `auto_extract: "false"` oraz wartości `off` i `0` nie uruchamiają ekstrakcji. Używany jest wspólny parser wartości logicznych Hermesa.
- Domyślna ścieżka w schemacie i zapisywanej konfiguracji to `$HERMES_HOME/memory_store.db`. Gdy formularz przekazuje konkretną domyślną ścieżkę bieżącego profilu, zapis normalizuje ją do tego wzorca. Skopiowana konfiguracja otwiera bazę nowego profilu. Jawnie wybrane niestandardowe ścieżki pozostają zachowane; istniejących baz ani starych konfiguracji nie przenosimy automatycznie.
- Zakończenie działania zamyka połączenie SQLite także wtedy, gdy inny obiekt nadal przechowuje referencję. Zapis YAML korzysta z istniejącego atomowego zapisu zamiast bezpośredniego nadpisania pliku.

Testy korzystają z prawdziwego SQLite. Przed poprawką 7 przypadków zawodziło; po poprawce przechodzi wszystkie 13 przypadków cyklu życia i izolacji profili.

### Odczyt historii bez migracji i zapisu

API `SessionDB(db_path=..., read_only=True)` umożliwia audyt historii przez istniejące metody `list_sessions_rich`, `get_messages` i odczyt tytułów. Jest to brakujący kontrakt znaleziony w `hermes-memory-wiki/dashboard/plugin_api.py`.

Tryb otwiera istniejący plik przez SQLite URI `mode=ro`, ustawia `query_only`, pomija tworzenie katalogu, migracje, ustawianie WAL i checkpointy. Publiczne operacje zapisu odrzuca od razu. Ścieżki są kodowane przez `Path.as_uri()`; nie używamy `immutable=1`, bo działający gateway może dopisywać do WAL. Nieudany odczyt nie nadpisuje globalnej diagnostyki inicjalizacji zapisywalnej bazy.

Pięć testów sprawdza odczyt publicznego API, brak zmiany istniejącego schematu/pliku, odmowę zapisu, brak tworzenia nieistniejącego profilu i widoczność nowych zatwierdzonych wiadomości WAL. To podstawa dla audytu; pełny plugin Memory Wiki oraz jego UI nie są instalowane ani aktywowane tą zmianą.

### Instalator dodatków

Instalator odczytuje `plugin.yml` tak samo jak `plugin.yaml`, używając nazwy manifestu i zachowując metadane. Manifest musi być mapą YAML.

Dodatek zawierający wyłącznie portable `plugin.json` lub Desktop `plugin.js` jest odrzucany z opisem brakującego runtime **przed** usunięciem istniejącej instalacji, również przy `force=True`. Natywny dodatek może nadal dołączać te pliki. Sprawdzanie jest ogólne i nie zawiera wyjątków według nazw zewnętrznych usług. Ta zmiana zapobiega pozornej instalacji; nie stanowi implementacji portable loadera.

## Kolejność dalszej integracji

1. **Rdzeń i pomiary.** Utrzymać zgodność obecnego agenta/Androida oraz nowe kontrakty. Dla przenoszonych poprawek narzędzi przygotować porównanie przypiętego baseline i wersji ze zmianą, z deterministycznym kryterium ukończenia zadania. Raportować skuteczność, błędy, liczbę tur, użycie i czas. Nie zastępować forka całą aktualną gałęzią upstream.
2. **Audyt pamięci.** Zweryfikować Memory Wiki wobec publicznego API, uwierzytelniania dashboardu i wyboru profilu. Potem udostępnić odczyt w docelowym kliencie. Zachować domyślną pamięć lokalną; użytkownik wybiera najwyżej jeden dodatkowy backend i zakres przesyłanych danych.
3. **Ogólne kontrakty dodatków.** Oddzielnie przenieść portable manifest/MCP, instalację z podkatalogu, przypinanie rewizji, kontrolę zależności i wykrywanie aplikacji. Dla Sprites dodać ogólny kontrakt środowisk terminala, a dla Telegram Business ogólną rejestrację handlerów. Nie dodawać specyficznych warunków usług do pętli agenta.
4. **Wybrane usługi.** Po sprawdzeniu powyższych kontraktów kwalifikować BackSearch, wybrany backend pamięci, Snyk lub Telegram Business na osobnych testowych zasobach. Do tego potrzebne są rzeczywiste konta/endpointy; ta analiza ich nie tworzy i niczego nie wysyła klientom.
5. **Zdalne inference i sandbox.** Łączyć telefon z serwerem vLLM przez istniejący własny endpoint. NemoClaw/OpenShell kwalifikować jako oddzielną infrastrukturę: polityki narzędzi, sieci, przechowywania i sekretów. Nie przenosić całego stosu kontenerowego do bazowej instalacji Androida.
6. **Oceny i trening.** Harbor i Gym są kandydatami do zewnętrznych ocen na izolowanych zadaniach. AutoModel/RL oraz trening drafterów mają oddzielne zależności i budżet sprzętowy. Adapter Gym ma wymagania śledzenia tokenów, próbkowania i braku niemotonicznych zmian historii; zwykła konfiguracja konwersacyjna nie jest automatycznie poprawna do RL.
7. **Marka, UI i język.** Dopiero po zakończeniu wybranych funkcji. Akcenty Desktop, roster botów oraz interfejs Memory Wiki są materiałem do tego etapu, nie zmianą nazwy teraz.

## Jak potwierdzać korzyści

`hermes-toolperf-evals/results/2026-08-06_rerun/README.md` jest ważniejszym punktem odniesienia niż nagłówek głównego README. Powtórzenie badań pokazuje wzrost skuteczności słabszego modelu w części zadań kosztem większej liczby tur i czasu; nie odtwarza wcześniejszej deklaracji przyspieszenia. Nie przypisujemy ODYN-AI wartości „−21% tur” ani innych procentów bez własnego porównania.

Dla każdego rozszerzenia potrzebne są: testy bez sieci dla błędów i izolacji, test integracyjny właściwej usługi, a dla twierdzeń dotyczących telefonu pomiar na fizycznym urządzeniu. Obsługa narzędzi, prawidłowy błąd i bezpieczeństwo zapisu są odrębnymi kryteriami od jakości odpowiedzi modelu.

## Weryfikacja tej partii

Wszystkie polecenia używają kanonicznego `scripts/run_tests.sh`. Lokalny zestaw magazynu sesji wraz z nowymi przypadkami: **217 passed**. Testy instalatora, jego regresji i cyklu życia pamięci dostępne w częściowym checkout: **72 passed**; nie obejmują sześciu wcześniej istniejących przypadków zależnych od niedostępnych lokalnie modułów całej aplikacji. Nowe przypadki: **22 passed**. W pełnym CI wykonywane są wszystkie testy, bez tych lokalnych wyłączeń.

Status pełnego CI dla tej partii zostanie zapisany w opisie odpowiadającego jej PR po wykonaniu kontroli. Osobno scalony wcześniejszy pakiet kontroli poznawczej i Androida przeszedł **25 229 testów**, **56 E2E** oraz **952 testy Python dotyczące Androida** i budowę APK. Żaden wynik tego przeglądu nie potwierdza jeszcze wydajności modelu GGUF na fizycznym telefonie.
