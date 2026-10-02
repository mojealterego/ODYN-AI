from __future__ import annotations
from dataclasses import dataclass
import base64, hashlib, secrets, time
from urllib.parse import urlencode
import httpx

@dataclass(frozen=True)
class OAuthAuthorizationRequest:
    url: str
    state: str
    code_verifier: str

@dataclass(frozen=True)
class OAuthToken:
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 300
    refresh_token: str | None = None
    scope: str | None = None
    issued_at: float = 0.0

    @property
    def expires_at(self) -> float:
        return self.issued_at + self.expires_in

class OAuthAuthorizationClient:
    def __init__(self, *, authorization_endpoint: str, token_endpoint: str, client_id: str, redirect_uri: str, scope: str = "", transport=None):
        self.authorization_endpoint=authorization_endpoint
        self.token_endpoint=token_endpoint
        self.client_id=client_id
        self.redirect_uri=redirect_uri
        self.scope=scope
        self.transport=transport
        self._pending: dict[str,str]={}
        self._token: OAuthToken|None=None

    @staticmethod
    def _challenge(verifier: str) -> str:
        return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    def create_authorization_request(self) -> OAuthAuthorizationRequest:
        verifier=secrets.token_urlsafe(48); state=secrets.token_urlsafe(32)
        self._pending[state]=verifier
        query=urlencode({"response_type":"code","client_id":self.client_id,"redirect_uri":self.redirect_uri,"scope":self.scope,"state":state,"code_challenge":self._challenge(verifier),"code_challenge_method":"S256"})
        return OAuthAuthorizationRequest(f"{self.authorization_endpoint}?{query}",state,verifier)

    async def exchange_code(self, code: str, state: str) -> OAuthToken:
        verifier=self._pending.pop(state,None)
        if not verifier: raise PermissionError("Nieprawidłowy lub wygasły stan OAuth.")
        async with httpx.AsyncClient(timeout=30, follow_redirects=False, transport=self.transport) as client:
            response=await client.post(self.token_endpoint,data={"grant_type":"authorization_code","code":code,"client_id":self.client_id,"redirect_uri":self.redirect_uri,"code_verifier":verifier},headers={"Accept":"application/json"})
            response.raise_for_status(); payload=response.json()
        self._token=OAuthToken(str(payload["access_token"]),str(payload.get("token_type","Bearer")),int(payload.get("expires_in",300)),payload.get("refresh_token"),payload.get("scope"),time.time())
        return self._token

    def restore_refresh_token(self, refresh_token: str) -> None:
        if not refresh_token:
            raise ValueError("Refresh token nie może być pusty.")
        self._token = OAuthToken(access_token="", expires_in=0, refresh_token=refresh_token, issued_at=time.time())

    async def refresh(self) -> OAuthToken:
        if not self._token or not self._token.refresh_token: raise PermissionError("Brak refresh tokena OAuth.")
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response=await client.post(self.token_endpoint,data={"grant_type":"refresh_token","refresh_token":self._token.refresh_token,"client_id":self.client_id},headers={"Accept":"application/json"})
            response.raise_for_status(); payload=response.json()
        self._token=OAuthToken(str(payload["access_token"]),str(payload.get("token_type",self._token.token_type)),int(payload.get("expires_in",300)),payload.get("refresh_token",self._token.refresh_token),payload.get("scope",self._token.scope),time.time())
        return self._token

    def authorization_header(self) -> str:
        if not self._token or time.time() >= self._token.expires_at-30: raise PermissionError("Token OAuth wygasł lub nie został uzyskany.")
        return f"{self._token.token_type} {self._token.access_token}"
