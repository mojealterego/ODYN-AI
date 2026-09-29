# ODYN AI

ODYN AI is the local-first agent layer inside hermes-agent.

## True dual-GGUF mode

Build/install llama-server from llama.cpp and put both files in odyn_ai/models:

- model_glowny_normany.gguf
- model_pomocniczy_maly.gguf

Run with ODYN_BACKEND=server. The engine starts llama-server with --model-draft and --spec-type draft-simple, which is the actual two-GGUF speculative path.

## Python fallback

Without llama-server or the draft GGUF, ODYN uses llama-cpp-python and LlamaPromptLookupDecoding. This is local speculative decoding, but it is not a neural two-GGUF draft model.

## Run

python -m odyn_ai.run

Open http://127.0.0.1:8000.
