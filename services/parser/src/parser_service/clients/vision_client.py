"""视觉模型客户端：将简历页面图片转换为可见文本。"""

from __future__ import annotations

import base64

from litellm import completion as litellm_completion

from parser_service.core.config import Settings


class VisionClient:
    def __init__(self, settings: Settings):
        if not settings.model_api_key:
            raise RuntimeError("扫描件需要 OCR，但没有配置 MODEL_API_KEY")
        self.model = (
            settings.ocr_model
            if "/" in settings.ocr_model
            else f"openai/{settings.ocr_model}"
        )
        self.api_key = settings.model_api_key
        self.api_base = settings.model_base_url.rstrip("/")
        self.timeout = settings.ocr_timeout_seconds

    def recognize_png(self, png: bytes) -> str:
        """识别单页 PNG 中的可见文字，不补写或推断缺失内容。"""
        encoded = base64.b64encode(png).decode("ascii")
        response = litellm_completion(
            model=self.model,
            api_key=self.api_key,
            api_base=self.api_base,
            timeout=self.timeout,
            num_retries=0,
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
                                "请识别这张简历图片中实际可见的全部文字，按照从上到下、"
                                "从左到右的阅读顺序输出纯文本。不要解释、推断或补充图片中"
                                "不存在的信息。"
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
