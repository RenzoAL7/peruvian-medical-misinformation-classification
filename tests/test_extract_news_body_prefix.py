import importlib.util
import os
import sys
import types
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "oci" / "functions" / "extract_news_body" / "func.py"


def _load_module() -> types.ModuleType:
    fdk = types.ModuleType("fdk")
    fdk.response = types.SimpleNamespace(Response=object)
    previous_fdk = sys.modules.get("fdk")
    sys.modules["fdk"] = fdk
    try:
        spec = importlib.util.spec_from_file_location("extract_news_body_func", MODULE_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if previous_fdk is None:
            sys.modules.pop("fdk", None)
        else:
            sys.modules["fdk"] = previous_fdk


def test_body_output_prefix_never_uses_generic_silver(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.delenv("SILVER_BODY_PREFIX", raising=False)
    monkeypatch.setenv("SILVER_PREFIX", "silver")

    assert module._body_output_prefix() == "silver/body"


def test_body_output_prefix_prefers_scoped_configuration(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.setenv("SILVER_PREFIX", "legacy/ignored")
    monkeypatch.setenv("SILVER_BODY_PREFIX", "/silver/body/")

    assert module._body_output_prefix() == "silver/body"


def test_body_output_prefix_keeps_an_explicit_legacy_subprefix(monkeypatch) -> None:
    module = _load_module()
    monkeypatch.delenv("SILVER_BODY_PREFIX", raising=False)
    monkeypatch.setenv("SILVER_PREFIX", "silver/body")

    assert module._body_output_prefix() == "silver/body"
