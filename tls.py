"""Strict TLS contexts for client, server, and replication connections."""

import ssl


def server_context(cert_file, key_file, ca_file=None, require_client_cert=False):
    """Create a server-side TLS context requiring a valid certificate chain."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(cert_file, key_file)
    if ca_file:
        context.load_verify_locations(cafile=ca_file)
    if require_client_cert:
        context.verify_mode = ssl.CERT_REQUIRED
    return context


def client_context(ca_file=None, cert_file=None, key_file=None):
    """Create a client-side TLS context with hostname verification enabled."""
    context = ssl.create_default_context(cafile=ca_file or None)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    if cert_file and key_file:
        context.load_cert_chain(cert_file, key_file)
    return context
