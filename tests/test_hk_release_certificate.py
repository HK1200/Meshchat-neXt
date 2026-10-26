"""Accept supported apksigner output formats without accepting other keys."""

import importlib.util
from pathlib import Path


def test_release_certificate_formats():
    path = Path(__file__).parents[1] / "scripts/ci/verify-next-release.py"
    spec = importlib.util.spec_from_file_location("hk_release_verify", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cert = "12" * 32
    assert module.certificate_matches(
        f"Signer #1 certificate SHA-256 digest: {cert}", cert
    )
    assert module.certificate_matches(
        f"Signer (minSdkVersion=24) certificate SHA-256 digest: {cert.upper()}", cert
    )
    assert module.certificate_matches(
        "Signer certificate SHA-256 digest: "
        + ":".join(cert[i : i + 2] for i in range(0, 64, 2)),
        cert,
    )
    assert not module.certificate_matches("", cert)
    assert not module.certificate_matches(
        "Signer #1 certificate SHA-256 digest: " + "0" * 64, cert
    )
    assert not module.certificate_matches(
        f"Signer #1 certificate SHA-256 digest: {cert}\nSigner #2 certificate SHA-256 digest: "
        + "0" * 64,
        cert,
    )
