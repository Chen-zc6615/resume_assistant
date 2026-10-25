import base64
from types import SimpleNamespace

from parser_service.clients import vision_client as vision_module
from parser_service.clients.vision_client import VisionClient


def test_recognize_png_uses_litellm_completion(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="识别后的简历文本"))]
        )

    monkeypatch.setattr(vision_module, "litellm_completion", fake_completion)
    settings = SimpleNamespace(
        ocr_model="qwen-vl-max",
        model_api_key="test-key",
        model_base_url="https://example.test/v1/",
        ocr_timeout_seconds=30.0,
    )
    client = VisionClient(settings)
    png = b"fake-png"

    result = client.recognize_png(png)

    assert result == "识别后的简历文本"
    assert captured["model"] == "openai/qwen-vl-max"
    assert captured["api_base"] == "https://example.test/v1"
    assert captured["num_retries"] == 0
    image_url = captured["messages"][0]["content"][0]["image_url"]["url"]
    assert image_url == f"data:image/png;base64,{base64.b64encode(png).decode('ascii')}"
