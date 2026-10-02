"""Offline contract tests. These do not prove real speech recognition works."""

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("filename,audio", [("clip.wav", b""), ("notes.txt", b"text")])
def test_bad_upload(filename, audio):
    assert client.post("/transcribe", files={"audio_file": (filename, audio)}).status_code == 400


def test_missing_key(monkeypatch):
    monkeypatch.delenv("GNANI_API_KEY", raising=False)
    assert client.post("/transcribe", files={"audio_file": ("clip.wav", b"test")}).status_code == 503


def test_provider_contract(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "offline-test-key")

    async def fake_post(self, url, **kwargs):
        assert url == "https://api.vachana.ai/stt/v3"
        assert kwargs["headers"] == {"X-API-Key-ID": "offline-test-key"}
        assert kwargs["data"] == {"language_code": "hi-IN"}
        assert kwargs["files"]["audio_file"][1] == b"test"
        return httpx.Response(200, json={"success": True, "transcript": "नमस्ते", "request_id": "test"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    response = client.post("/transcribe", files={"audio_file": ("clip.wav", b"test")}, data={"language_code": "hi-IN"})
    assert response.status_code == 200
    assert response.json()["transcript"] == "नमस्ते"


@pytest.mark.parametrize("upstream,expected", [(403, 503), (429, 429), (500, 502)])
def test_provider_errors(monkeypatch, upstream, expected):
    monkeypatch.setenv("GNANI_API_KEY", "offline-test-key")

    async def fake_post(self, *args, **kwargs):
        return httpx.Response(upstream)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    response = client.post("/transcribe", files={"audio_file": ("clip.wav", b"test")})
    assert response.status_code == expected
    assert "detail" in response.json()


def test_timeout(monkeypatch):
    monkeypatch.setenv("GNANI_API_KEY", "offline-test-key")

    async def fake_post(self, *args, **kwargs):
        raise httpx.ReadTimeout("test timeout")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    assert client.post("/transcribe", files={"audio_file": ("clip.wav", b"test")}).status_code == 504
