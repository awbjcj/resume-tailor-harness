"""Public-only, DNS-pinned sockets for user-configured IMAP/SMTP servers."""

import imaplib
import smtplib
import socket
import ssl

from resume_tailor_harness.security.outbound import resolve_public_url

TIMEOUT = 20


def public_socket(host: str, port: int) -> socket.socket:
    # Reuse the central public-address policy, then connect to the validated IP.
    _, address, _ = resolve_public_url(f"https://{host}:{port}")
    return socket.create_connection((address, port), timeout=TIMEOUT)


class _BoundedIMAP(imaplib.IMAP4):
    def read(self, size):
        if size > 128 * 1024:
            raise imaplib.IMAP4.abort("Oversized IMAP literal")
        return super().read(size)


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
