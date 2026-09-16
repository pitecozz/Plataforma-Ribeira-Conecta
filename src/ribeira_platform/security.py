from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse


class SSRFBlocked(ValueError):
    pass


@dataclass(frozen=True)
class NetworkPolicy:
    allowed_hosts: frozenset[str] = frozenset()
    allow_private_hosts: bool = False

    def validate(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise SSRFBlocked("only http/https URLs with a hostname are permitted")
        hostname = parsed.hostname.rstrip(".").lower()
        if self.allowed_hosts and hostname not in self.allowed_hosts:
            raise SSRFBlocked("provider host is not in the allowlist")
        if hostname in {"localhost", "metadata.google.internal"}:
            raise SSRFBlocked("local and metadata hosts are blocked")
        try:
            addresses = {
                item[4][0]
                for item in socket.getaddrinfo(
                    hostname,
                    parsed.port or (443 if parsed.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                )
            }
        except socket.gaierror as exc:
            raise SSRFBlocked("provider hostname could not be resolved") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not self.allow_private_hosts and (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_unspecified
                or ip.is_reserved
            ):
                raise SSRFBlocked("provider resolves to a non-public network")
