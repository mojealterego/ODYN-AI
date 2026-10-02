from __future__ import annotations
import asyncio
import sys
import uvicorn

def configure_event_loop() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    configure_event_loop()
    uvicorn.run("odyn_ai.api.server:app", host="127.0.0.1", port=8000, reload=False, log_level="info")
