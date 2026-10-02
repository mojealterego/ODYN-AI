# ODYN AI

ODYN AI to lokalna warstwa agentowa w repozytorium **hermes-agent**.

## Tryb dwóch modeli GGUF

Zbuduj lub zainstaluj **llama-server** z projektu llama.cpp i umieść oba pliki w katalogu `odyn_ai/models`:

- `model_glowny_normany.gguf`
- `model_pomocniczy_maly.gguf`

Uruchom aplikację z `ODYN_BACKEND=server`. Silnik uruchomi `llama-server` z parametrami `--model-draft` i `--spec-type draft-simple`. Jest to właściwa ścieżka dekodowania spekulatywnego z dwoma modelami GGUF.

## Tryb awaryjny Python

Jeżeli `llama-server` lub pomocniczy model GGUF nie są dostępne, ODYN AI użyje `llama-cpp-python` i `LlamaPromptLookupDecoding`. Jest to lokalne dekodowanie spekulatywne, ale **nie jest to neuronowy model pomocniczy GGUF**.

## Uruchomienie

```bash
python -m odyn_ai.run
```

Następnie otwórz w przeglądarce:

`http://127.0.0.1:8000`

Interfejs użytkownika i komunikaty aplikacji są prowadzone po polsku.
