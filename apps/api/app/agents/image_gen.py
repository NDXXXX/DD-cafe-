import asyncio
import base64
from typing import Any

import httpx
from openai import AsyncOpenAI, OpenAIError

DASHSCOPE_API_URL = "https://dashscope.aliyuncs.com/api/v1"


class ImageGenModel:
    """Text-to-image generation via DashScope (qwen-image / wanx)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        size: str = "1328*1328",
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.size = size
        self.api_key = api_key

    async def generate_image(self, prompt: str) -> bytes:
        # Primary: OpenAI-compatible images endpoint (synchronous).
        try:
            response = await self.client.images.generate(
                model=self.model,
                prompt=prompt,
                size=self.size,
                n=1,
            )
            data = response.data[0]
            if getattr(data, "b64_json", None):
                return base64.b64decode(data.b64_json)
            if getattr(data, "url", None):
                return await self._download(data.url)
        except (OpenAIError, AttributeError, IndexError):
            pass
        # Fallback: native DashScope async text-to-image API.
        return await self._generate_native(prompt)

    async def _download(self, url: str) -> bytes:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

    async def _generate_native(self, prompt: str) -> bytes:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=60) as client:
            submit = await client.post(
                f"{DASHSCOPE_API_URL}/services/aigc/text2image/image-synthesis",
                headers={**headers, "X-DashScope-Async": "enable"},
                json={
                    "model": self.model,
                    "input": {"prompt": prompt},
                    "parameters": {"size": self.size, "n": 1},
                },
            )
            submit.raise_for_status()
            task_id = submit.json()["output"]["task_id"]

            for _ in range(60):
                await asyncio.sleep(2)
                poll = await client.get(
                    f"{DASHSCOPE_API_URL}/tasks/{task_id}",
                    headers=headers,
                )
                poll.raise_for_status()
                output: dict[str, Any] = poll.json()["output"]
                status = output.get("task_status")
                if status == "SUCCEEDED":
                    return await self._download(output["results"][0]["url"])
                if status in {"FAILED", "CANCELED"}:
                    raise RuntimeError(output.get("message", "image generation failed"))
        raise TimeoutError("image generation timed out")
