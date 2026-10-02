from __future__ import annotations
import ipaddress, socket
from urllib.parse import urlparse
import httpx

class SSRFPolicy:
    def __init__(self, *, allow_private:bool=False): self.allow_private=allow_private
    def validate_url(self,url:str)->tuple[str,list[ipaddress._BaseAddress]]:
        parsed=urlparse(url)
        if parsed.scheme not in {"http","https"} or not parsed.hostname: raise ValueError("Adres musi być HTTP/HTTPS i zawierać hostname.")
        if parsed.username or parsed.password: raise PermissionError("URL nie może zawierać credentials.")
        try: infos=socket.getaddrinfo(parsed.hostname,parsed.port or (443 if parsed.scheme=="https" else 80),type=socket.SOCK_STREAM)
        except OSError as exc: raise PermissionError(f"Nie można bezpiecznie rozwiązać hosta {parsed.hostname}.") from exc
        addresses=[]
        for info in infos:
            addr=ipaddress.ip_address(info[4][0])
            if addr not in addresses: addresses.append(addr)
        self.validate_addresses(addresses)
        return parsed.hostname,addresses
    def validate_addresses(self,addresses:list[ipaddress._BaseAddress])->None:
        for address in addresses:
            if not self.allow_private and (address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved or address.is_private):
                raise PermissionError(f"Adres {address} jest zablokowany przez politykę SSRF.")


class PinnedAsyncHTTPTransport(httpx.AsyncHTTPTransport):
    """Connect to a validated IP while preserving hostname/SNI for TLS and HTTP."""

    def __init__(self, policy: SSRFPolicy, **kwargs):
        super().__init__(**kwargs)
        self.policy = policy

    def pin_request(self, request: httpx.Request) -> httpx.Request:
        hostname = request.url.host
        _, addresses = self.policy.validate_url(str(request.url))
        if not addresses:
            raise PermissionError("Brak bezpiecznego adresu docelowego.")
        target = str(addresses[0])
        request.extensions["sni_hostname"] = hostname
        request.headers["Host"] = hostname if request.url.port in (None, 80, 443) else f"{hostname}:{request.url.port}"
        request.url = request.url.copy_with(host=target)
        return request

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return await super().handle_async_request(self.pin_request(request))
