"""Public-only, DNS-pinned sockets for user-configured IMAP/SMTP servers."""

import imaplib
import smtplib
import socket
import ssl
from contextlib import contextmanager
from dataclasses import dataclass
from collections.abc import Callable
from typing import BinaryIO, cast

from resume_tailor_harness.security.outbound import resolve_public_url

TIMEOUT = 20
IMAP_LITERAL_LIMIT = 128 * 1024
IMAP_BATCH_SIZE = 8


@dataclass
class _ResponseBudget:
    checkpoint: Callable[[], None]
    literal_bytes: int = IMAP_LITERAL_LIMIT * IMAP_BATCH_SIZE
    literals: int = IMAP_BATCH_SIZE
    overhead: int = 64 * 1024


def public_socket(host: str, port: int) -> socket.socket:
    # Reuse the central public-address policy, then connect to the validated IP.
    _, address, _ = resolve_public_url(f"https://{host}:{port}")
    return socket.create_connection((address, port), timeout=TIMEOUT)


class _BoundedIMAP(imaplib.IMAP4):
    _response_budget: _ResponseBudget | None = None

    @contextmanager
    def bounded_response(self, checkpoint):
        """Bound a FETCH command before imaplib buffers its literals/lines."""
        self._response_budget = _ResponseBudget(checkpoint)
        try:
            yield
        finally:
            self._response_budget = None

    def read(self, size):
        if size > IMAP_LITERAL_LIMIT:
            raise imaplib.IMAP4.abort("Oversized IMAP literal")
        budget = self._response_budget
        if budget is not None:
            budget.checkpoint()
            if size > budget.literal_bytes or budget.literals <= 0:
                raise imaplib.IMAP4.abort("Oversized IMAP response")
            budget.literal_bytes -= size
            budget.literals -= 1
        result = super().read(size)
        if budget is not None:
            budget.checkpoint()
        return result

    def readline(self):
        budget = self._response_budget
        if budget is None:
            return super().readline()
        budget.checkpoint()
        # Limit the allocation itself, not just the completed response.
        line = cast(BinaryIO, self.file).readline(budget.overhead + 1)
        if len(line) > budget.overhead:
            raise imaplib.IMAP4.abort("Oversized IMAP response metadata")
        budget.overhead -= len(line)
        budget.checkpoint()
        return line


class PublicIMAP(_BoundedIMAP):
    def _create_socket(self, timeout):
        return public_socket(self.host, self.port)


class PublicIMAPSSL(imaplib.IMAP4_SSL, _BoundedIMAP):
    def _create_socket(self, timeout):
        sock = public_socket(self.host, self.port)
        try:
            return self.ssl_context.wrap_socket(sock, server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


class PublicSMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        return public_socket(host, port)


class PublicSMTPSSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        sock = public_socket(host, port)
        try:
            return self.context.wrap_socket(sock, server_hostname=host)
        except BaseException:
            sock.close()
            raise


def tls_context() -> ssl.SSLContext:
    return ssl.create_default_context()
