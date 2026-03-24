"""FastAPI routes for model governance portal."""

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/models", tags=["models"])

# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------

_REGISTRY_PATH = Path(__file__).parent.parent / "model_docs" / "registry.json"
_DOCS_DIR = Path(__file__).parent.parent / "model_docs" / "xva"
_ALLOWED_SUFFIXES = {".tex", ".md", ".pdf"}


def _load_registry() -> dict[str, Any]:
    with _REGISTRY_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _get_model(model_id: str) -> dict[str, Any]:
    registry = _load_registry()
    for model in registry["models"]:
        if model["id"] == model_id:
            return model
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/registry")
def get_registry() -> dict[str, Any]:
    """Return the full model registry JSON."""
    return _load_registry()


@router.get("/stats")
def get_stats() -> dict[str, Any]:
    """Return summary statistics across all registered models."""
    registry = _load_registry()
    models = registry["models"]

    by_status: dict[str, int] = {}
    open_findings_total = 0
    critical_open = 0
    tier1_count = 0

    for model in models:
        status = model.get("status", "unknown")
        by_status[status] = by_status.get(status, 0) + 1

        open_findings_total += model.get("open_findings", 0)

        if model.get("tier") == 1:
            tier1_count += 1

        for finding in model.get("findings", []):
            if finding.get("severity") == "critical" and finding.get("status") == "open":
                critical_open += 1

    return {
        "total_models": registry["metadata"]["total_models"],
        "by_status": by_status,
        "open_findings_total": open_findings_total,
        "critical_open": critical_open,
        "tier1_count": tier1_count,
    }


@router.get("/{model_id}")
def get_model(model_id: str) -> dict[str, Any]:
    """Return a single model record by ID (e.g. APEX-MDL-0014)."""
    return _get_model(model_id)


@router.get("/{model_id}/findings")
def get_findings(model_id: str) -> list[dict[str, Any]]:
    """Return the findings list for a specific model."""
    model = _get_model(model_id)
    return model.get("findings", [])


@router.get("/{model_id}/doc/{filename}")
def get_doc(model_id: str, filename: str) -> FileResponse:
    """Serve a model document file (.tex, .md, or .pdf) for the given model."""
    # Validate model exists
    model = _get_model(model_id)

    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{suffix}' is not permitted. Allowed: {sorted(_ALLOWED_SUFFIXES)}",
        )

    if filename not in model.get("doc_files", []):
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' is not registered for model '{model_id}'",
        )

    file_path = (_DOCS_DIR / filename).resolve()
    if not str(file_path).startswith(str(_DOCS_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Document file '{filename}' not found on disk")

    media_type_map = {
        ".tex": "text/plain",
        ".md": "text/plain",
        ".pdf": "application/pdf",
    }

    return FileResponse(
        path=str(file_path),
        media_type=media_type_map.get(suffix, "application/octet-stream"),
        filename=filename,
    )
