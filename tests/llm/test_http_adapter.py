"""HTTP adapter scenarios using deterministic responses and no paid calls."""

import httpx
import pytest

from sql_tutor.llm import HTTPChatLLM


class _Response:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self.payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("fake HTTP error", request=httpx.Request("POST", "http://fake"), response=httpx.Response(self.status_code))

    def json(self):
        return self.payload


def test_http_adapter_retries_rate_limits_but_not_unauthorized(monkeypatch):
    responses = iter([_Response(429), _Response(200, {"choices": [{"message": {"content": '{"message":"ok"}'}}]})])
    calls = []
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: calls.append(kwargs) or next(responses))
    monkeypatch.setattr("sql_tutor.llm.time.sleep", lambda _: None)

    assert HTTPChatLLM("http://fake", "model", None, 1, 2).complete("chat", {}) == {"message": "ok"}
    assert len(calls) == 2

    unauthorized_calls = []
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: unauthorized_calls.append(kwargs) or _Response(401))
    with pytest.raises(httpx.HTTPStatusError):
        HTTPChatLLM("http://fake", "model", None, 1, 3).complete("chat", {})
    assert len(unauthorized_calls) == 1


def test_http_adapter_rejects_malformed_json_after_budget(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: _Response(200, {"choices": [{"message": {"content": "not-json"}}]}))
    monkeypatch.setattr("sql_tutor.llm.time.sleep", lambda _: None)

    with pytest.raises(ValueError):
        HTTPChatLLM("http://fake", "model", None, 1, 2).complete("chat", {})