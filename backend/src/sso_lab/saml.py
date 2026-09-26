"""SAML 2.0 plumbing shared by the IdP and the apps: XML parsing, bindings, signing keys.

The messages themselves are built by hand in ``idp/saml.py`` and ``rp/saml.py`` so they can be
read; XML Signature is done by ``signxml``.
"""

import base64
import secrets
import zlib
from datetime import UTC, datetime, timedelta

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import SignatureConfiguration, XMLSigner, XMLVerifier
from signxml.algorithms import CanonicalizationMethod, DigestAlgorithm, SignatureMethod

from sso_lab.lab.store import Store

NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "md": "urn:oasis:names:tc:SAML:2.0:metadata",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}
BINDING_REDIRECT = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
BINDING_POST = "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST"
NAMEID_EMAIL = "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress"
STATUS_SUCCESS = "urn:oasis:names:tc:SAML:2.0:status:Success"
AUTHN_CONTEXT_PPT = "urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport"

# Only what this IdP uses. Anything weaker (SHA-1) or symmetric (HMAC) is refused.
EXPECT_SIGNATURE = SignatureConfiguration(
    signature_methods=frozenset({SignatureMethod.RSA_SHA256}),
    digest_algorithms=frozenset({DigestAlgorithm.SHA256}),
    expect_references=1,
)


class UnsafeXml(ValueError):
    pass


def parse(data: bytes) -> etree._Element:
    """Parse untrusted XML safely: no DTDs, no entities, no network (XXE defenses)."""
    if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise UnsafeXml("DTDs and entities are not allowed in SAML messages")
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        load_dtd=False,
        huge_tree=False,
        remove_comments=False,
    )
    return etree.fromstring(data, parser=parser)


def pretty(xml: bytes | etree._Element) -> str:
    element = parse(xml) if isinstance(xml, bytes) else xml
    return etree.tostring(element, pretty_print=True, encoding="unicode")


def new_id() -> str:
    # XML IDs must not start with a digit.
    return "_" + secrets.token_hex(16)


def instant(moment: datetime | None = None) -> str:
    return (moment or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_instant(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.replace(".000", ""), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None


# --- Bindings ---------------------------------------------------------------------------


def encode_redirect(xml: bytes) -> str:
    """HTTP-Redirect binding: raw DEFLATE, then base64 (the caller URL-encodes)."""
    compressor = zlib.compressobj(wbits=-15)
    return base64.b64encode(compressor.compress(xml) + compressor.flush()).decode()


def decode_redirect(value: str) -> bytes:
    inflater = zlib.decompressobj(wbits=-15)
    data = inflater.decompress(base64.b64decode(value), 256 * 1024)
    if inflater.unconsumed_tail:
        raise UnsafeXml("SAMLRequest is too large")
    return data


def encode_post(xml: bytes) -> str:
    """HTTP-POST binding: plain base64."""
    return base64.b64encode(xml).decode()


def decode_post(value: str) -> bytes:
    return base64.b64decode(value, validate=False)


# --- The IdP's signing key and certificate --------------------------------------------------

_KIND = "samlKeys"


async def idp_credentials(store: Store) -> tuple[str, str]:
    """(private key PEM, certificate PEM), created once and shared by every IdP instance."""
    record = await store.get_record(_KIND, "current")
    if record is None:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "SSO Lab teaching IdP")])
        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .sign(key, hashes.SHA256())
        )
        await store.create_record(
            _KIND,
            "current",
            {
                "key_pem": key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                ).decode(),
                "cert_pem": cert.public_bytes(serialization.Encoding.PEM).decode(),
            },
            ttl=None,
        )
        record = await store.get_record(_KIND, "current")
        assert record is not None
    return record["key_pem"], record["cert_pem"]


def cert_body(cert_pem: str) -> str:
    """The base64 body of a PEM certificate, as metadata's <ds:X509Certificate> wants it."""
    return "".join(line for line in cert_pem.strip().splitlines() if "CERTIFICATE" not in line)


def cert_pem_from_body(body: str) -> str:
    compact = "".join(body.split())
    lines = [compact[i : i + 64] for i in range(0, len(compact), 64)]
    return "-----BEGIN CERTIFICATE-----\n" + "\n".join(lines) + "\n-----END CERTIFICATE-----\n"


def sign(element: etree._Element, key_pem: str, cert_pem: str) -> etree._Element:
    """Enveloped signature over ``element`` (by its ID), placed at its ds:Signature placeholder."""
    signer = XMLSigner(c14n_algorithm=CanonicalizationMethod.EXCLUSIVE_XML_CANONICALIZATION_1_0)
    return signer.sign(
        element,
        key=key_pem.encode(),
        cert=cert_pem,
        reference_uri=element.get("ID"),
        id_attribute="ID",
    )


def verify(xml: bytes, cert_pem: str) -> etree._Element:
    """Verify the one signature in ``xml`` against ``cert_pem``; returns the element it covers.

    Callers must read data only from the returned element. It is the only part of the document
    the signature vouches for (this is the defense against XML Signature Wrapping).
    """
    result = XMLVerifier().verify(
        xml, x509_cert=cert_pem, expect_config=EXPECT_SIGNATURE, id_attribute="ID"
    )
    return result.signed_xml  # type: ignore[union-attr]
