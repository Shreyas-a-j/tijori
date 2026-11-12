"""API-key gate, audit retention, and monitoring signal tests."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.audit.retention import main as retention_main
from app.contracts import AuditRecord


def _record(
    request_id: str,
    created_at: str,
    *,
    status: str = "ok",
    leakage_count: int = 0,
) -> AuditRecord:
    return AuditRecord(
        request_id=request_id,
        created_at=created_at,
        status=status,
        leakage_count=leakage_count,
    )


def _utc_timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def test_api_key_authentication_and_unset_default(gateway, monkeypatch) -> None:
    client, _provider, _repository = gateway
    monkeypatch.setenv("TIJORI_API_KEY", "expected-secret")

    missing = client.get("/v1/audit")
    assert missing.status_code == 401
    assert missing.json() == {"detail": "unauthorized"}
    assert missing.headers["www-authenticate"] == "X-API-Key"
    assert client.get("/v1/audit", headers={"X-API-Key": "wrong-secret"}).status_code == 401
    assert client.get("/v1/audit", headers={"X-API-Key": "expected-secret"}).status_code == 200
    assert client.get("/health").status_code == 200

    monkeypatch.delenv("TIJORI_API_KEY")
    assert client.get("/health").status_code == 200
    assert client.get("/v1/audit").status_code == 200
    assert client.post("/v1/sanitize", json={"text": "No sensitive data."}).status_code == 200
    assert client.post(
        "/v1/process",
        json={"text": "No sensitive data.", "task": "summarize"},
    ).status_code == 200


def test_purge_older_than_dry_run_and_delete(gateway) -> None:
    _client, _provider, repository = gateway
    now = datetime.now(timezone.utc)
    old = _record("req_old", _utc_timestamp(now - timedelta(days=400)))
    new = _record("req_new", _utc_timestamp(now))
    repository.insert(old)
    repository.insert(new)

    assert repository.purge_older_than(365, dry_run=True) == 1
    assert repository.get("req_old") is not None
    assert repository.get("req_new") is not None

    assert repository.purge_older_than(365) == 1
    assert repository.get("req_old") is None
    assert repository.get("req_new") is not None


def test_retention_cli_exits_successfully(gateway, capsys) -> None:
    _client, _provider, repository = gateway

    exit_code = retention_main(
        ["--days", "365", "--dry-run", "--db-path", repository.db_path]
    )

    assert exit_code == 0
    assert "would purge 0 rows older than 365 days" in capsys.readouterr().out


def test_leakage_record_emits_one_pii_free_warning(gateway, caplog) -> None:
    client, _provider, repository = gateway
    repository.insert(
        _record("req_leak", _utc_timestamp(datetime.now(timezone.utc)), leakage_count=1)
    )
    caplog.set_level(logging.WARNING, logger="tijori.gateway")

    response = client.get("/v1/audit/req_leak")

    assert response.status_code == 200
    assert len(caplog.records) == 1
    warning = caplog.records[0]
    assert warning.levelno == logging.WARNING
    assert warning.request_id == "req_leak"
    assert warning.leakage_count == 1
    assert "Rahul Sharma" not in caplog.text
    assert "1234-5678-9012" not in caplog.text


def test_error_record_emits_one_pii_free_warning(gateway, caplog) -> None:
    client, _provider, repository = gateway
    repository.insert(
        _record("req_error", _utc_timestamp(datetime.now(timezone.utc)), status="error")
    )
    caplog.set_level(logging.WARNING, logger="tijori.gateway")

    response = client.get("/v1/audit/req_error")

    assert response.status_code == 200
    assert len(caplog.records) == 1
    warning = caplog.records[0]
    assert warning.levelno == logging.WARNING
    assert warning.request_id == "req_error"
    assert warning.leakage_count == 0
    assert warning.status == "error"
    assert "Rahul Sharma" not in caplog.text
    assert "1234-5678-9012" not in caplog.text


def test_provider_failure_emits_one_pii_free_warning(gateway, caplog) -> None:
    client, provider, repository = gateway
    provider.error = RuntimeError("provider failed for Rahul Sharma / 1234-5678-9012")
    caplog.set_level(logging.WARNING, logger="tijori.gateway")

    response = client.post(
        "/v1/process",
        json={"text": "No sensitive data.", "task": "summarize"},
    )

    assert response.status_code == 502
    assert len(caplog.records) == 1
    warning = caplog.records[0]
    assert warning.levelno == logging.WARNING
    assert warning.request_id == repository.list()[0].request_id
    assert warning.leakage_count == 0
    assert warning.status == "error"
    assert "Rahul Sharma" not in caplog.text
    assert "1234-5678-9012" not in caplog.text