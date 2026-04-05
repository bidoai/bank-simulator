from __future__ import annotations

from fastapi.testclient import TestClient


def test_model_pdf_downloads_compiled_pdf():
    from api.main import app

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/api/models/APEX-MDL-0004/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "mdd_black_scholes_v1.0.pdf" in resp.headers["content-disposition"]


def test_model_pdf_falls_back_to_xva_pdf_artifact():
    from api.main import app

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/api/models/APEX-MDL-0014/pdf")

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert "mdd_pfe_ccr_v1.0.pdf" in resp.headers["content-disposition"]


def test_model_doc_route_serves_registered_markdown_from_root_docs_dir():
    from api.main import app

    client = TestClient(app, raise_server_exceptions=True)
    resp = client.get("/api/models/APEX-MDL-0004/doc/mdd_black_scholes_v1.0.md")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
