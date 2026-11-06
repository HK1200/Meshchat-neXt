# SPDX-License-Identifier: 0BSD
"""Synthetic guard failures; native SDK execution has separate release evidence."""

import platform
import pyexpat
import xml.etree.ElementTree as ET

import pytest

from meshchatnext.src.backend.frozen_freeze_probe import _verify_security_parser


@pytest.fixture
def fixed_versions(monkeypatch):
    monkeypatch.setattr(platform, "python_version", lambda: "3.14.10")
    monkeypatch.setattr(pyexpat, "EXPAT_VERSION", "expat_2.10.0")


def test_parser_guard_checks_valid_and_invalid_xml(fixed_versions):
    assert _verify_security_parser() == {"python": "3.14.10", "expat": "expat_2.10.0"}


@pytest.mark.parametrize(
    "component,value", [("python", "3.14.7"), ("expat", "expat_2.9.0")]
)
def test_parser_guard_rejects_old_runtime(
    monkeypatch, fixed_versions, component, value
):
    if component == "python":
        monkeypatch.setattr(platform, "python_version", lambda: value)
    else:
        monkeypatch.setattr(pyexpat, "EXPAT_VERSION", value)
    with pytest.raises(RuntimeError, match="Frozen runtime is not security fixed"):
        _verify_security_parser()


def test_parser_guard_rejects_broken_elementtree_api(monkeypatch, fixed_versions):
    monkeypatch.setattr(ET, "fromstring", lambda _: ET.Element("wrong"))
    with pytest.raises(RuntimeError, match="native parser Unicode check failed"):
        _verify_security_parser()


@pytest.mark.parametrize("fault", ["malformed", "amplification", "wrong-error"])
def test_parser_guard_rejects_missing_xml_protections(
    monkeypatch, fixed_versions, fault
):
    real_factory = pyexpat.ParserCreate

    class FaultyParser:
        def Parse(self, text, final):
            if text == "<root>" and fault == "malformed":
                return None
            if text.startswith("<!DOCTYPE"):
                if fault == "amplification":
                    return None
                if fault == "wrong-error":
                    error = pyexpat.ExpatError("synthetic unexpected parser error")
                    error.code = pyexpat.errors.codes[pyexpat.errors.XML_ERROR_SYNTAX]
                    raise error
            return real_factory().Parse(text, final)

    monkeypatch.setattr(pyexpat, "ParserCreate", FaultyParser)
    with pytest.raises(RuntimeError):
        _verify_security_parser()
