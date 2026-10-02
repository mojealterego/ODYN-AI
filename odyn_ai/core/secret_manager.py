from __future__ import annotations
import importlib

class NativeSecretManager:
    """OS credential store. Never falls back to plaintext files."""
    def __init__(self, *, service: str="odyn-ai", backend=None):
        self.service=service
        if backend is None:
            try: backend=importlib.import_module("keyring")
            except ImportError as exc: raise RuntimeError("Brak natywnego Secret Managera/keyring.") from exc
        self.backend=backend
    def get(self,name:str)->str|None: return self.backend.get_password(self.service,name)
    def set(self,name:str,value:str)->None:
        if not value: raise ValueError("Sekret nie może być pusty.")
        self.backend.set_password(self.service,name,value)
    def delete(self,name:str)->None:
        try: self.backend.delete_password(self.service,name)
        except Exception as exc:
            if "not found" not in str(exc).lower(): raise
    def require(self,name:str)->str:
        value=self.get(name)
        if not value: raise RuntimeError(f"Brak sekretu w natywnym Secret Managerze: {name}")
        return value
