from __future__ import annotations

import base64

from openai import OpenAI

from parser_service.core.config import Settings


class OCRClient:
    def __init__(self, settings: Settings):
        if not settings.model_api_key:
            raise RuntimeError("扫描件需要 OCR，但没有配置 MODEL_API_KEY")
        self.model = settings.ocr_model
        self.client = OpenAI(
            api_key=settings.model_api_key,
            base_url=settings.model_base_url.rstrip("/"),
            timeout=settings.parse_timeout_seconds,
            max_retries=0,
        )

    def recognize_png(self, png: bytes) -> str:
        encoded = base64.b64encode(png).decode("ascii")
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{encoded}"},
                        },
                        {
                            "type": "text",
                            "text": (
                                "请识别这张简历图片中的全部文字，按照从上到下、"
                                "从左到右的阅读顺序输出纯文本，不要解释。"
                            ),
                        },
                    ],
                }
            ],
            temperature=0.1,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("OCR 模型返回了空内容")
        return content

