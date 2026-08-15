from typing import Any

import httpx

from app.agents.vision import encode_image_data_url

DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/api/v1"

EDIT_PROMPT = (
    "把这张照片处理成温馨治愈的咖啡馆打卡照片：暖色调、柔和自然光、细腻的胶片质感，"
    "保留原照片的主体与构图，让画面更温暖、更有氛围感。"
)


class ImageEditModel:
    """Image editing (图生图) via DashScope Qwen-Image-Edit."""

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    async def generate_edit(self, image_path: str, prompt: str = EDIT_PROMPT) -> bytes:
        image_url = encode_image_data_url(image_path)
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                f"{DASHSCOPE_API_URL}/services/aigc/multimodal-generation/generation",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": {
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"image": image_url},
                                    {"text": prompt},
                                ],
                            }
                        ]
                    },
                },
            )
            response.raise_for_status()
            payload: dict[str, Any] = response.json()
            result_url = payload["output"]["choices"][0]["message"]["content"][0]["image"]
            download = await client.get(result_url)
            download.raise_for_status()
            return download.content
