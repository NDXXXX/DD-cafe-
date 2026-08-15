import base64
import json
import mimetypes
from typing import Any

from openai import AsyncOpenAI, OpenAIError


def encode_image_data_url(local_path: str) -> str:
    """Read an image file and return it as a base64 data URL."""
    mime_type, _ = mimetypes.guess_type(local_path)
    if mime_type is None or not mime_type.startswith("image/"):
        mime_type = "image/jpeg"
    with open(local_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


class VisionModel:
    """Analyse images via a vision-capable LLM before the LangGraph graph runs.

    Output is a text description fed into the existing recommendation agent,
    so the core cafe persona and graph structure stay unchanged.
    """

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def analyze_images(
        self,
        image_paths: list[str],
        user_message: str,
    ) -> dict[str, str]:
        """Return a dict with ``description`` and ``caption`` keys.

        ``description`` feeds into the LangGraph agent as extra context.
        ``caption`` (≤15 Chinese characters) is used for the check-in card.
        """
        user_content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "你是DD咖啡馆的打卡助手。用户上传了在咖啡馆的照片。"
                    "请用温暖、简洁的中文描述这张（这些）照片，语气要像朋友在夸赞。"
                    "同时生成一条适合用作「打卡卡片」的短文案（15字以内）。"
                    "请严格按照如下 JSON 格式输出，不要输出任何其他内容：\n"
                    '{"description": "描述内容", "caption": "15字以内的打卡文案"}'
                ),
            }
        ]
        for path in image_paths:
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": encode_image_data_url(path), "detail": "auto"},
                }
            )

        if user_message.strip():
            user_content.append(
                {"type": "text", "text": f"用户说：{user_message}"}
            )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": user_content}],
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
            payload = json.loads(raw)
            return {
                "description": str(payload.get("description", "")).strip(),
                "caption": str(payload.get("caption", ""))[:15],
            }
        except (OpenAIError, json.JSONDecodeError, KeyError):
            fallback = "用户上传了照片。请根据照片氛围给予温暖回应。"
            return {"description": fallback, "caption": ""}
