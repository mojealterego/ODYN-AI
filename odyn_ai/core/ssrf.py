from __future__ import annotations
import ipaddress, socket
from urllib.parse import urlparse

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
