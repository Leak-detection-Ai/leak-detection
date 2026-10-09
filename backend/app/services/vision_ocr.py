import base64
import logging

import httpx
from PIL import Image

from app.core.config import settings


logger = logging.getLogger(__name__)

OPENROUTER_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)

MAX_IMAGE_BYTES = 6 * 1024 * 1024

SUPPORTED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
}


async def extract_text_from_image_url(
    image_url: str,
) -> str:
    if not settings.openrouter_api_key:
        logger.warning(
            "OpenRouter image OCR skipped: API key is not configured"
        )
        return ""

    if not image_url or not image_url.startswith(
        ("http://", "https://")
    ):
        return ""

    try:
        timeout = httpx.Timeout(
            connect=5.0,
            read=15.0,
            write=15.0,
            pool=10.0,
        )

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                image_url,
                headers={
                    "User-Agent":
                        "LeakGuard/1.1 image-analysis"
                },
            )
            response.raise_for_status()

        image_bytes = response.content

        if len(image_bytes) > MAX_IMAGE_BYTES:
            logger.warning(
                "Mastodon image exceeds size limit"
            )
            return ""

        content_type = (
            response.headers
            .get("content-type", "")
            .split(";")[0]
            .lower()
        )

        if content_type not in SUPPORTED_MIME_TYPES:
            logger.warning(
                "Unsupported image MIME type: %s",
                content_type,
            )
            return ""

        image = Image.open(
            __import__("io").BytesIO(image_bytes)
        )
        image.verify()

        encoded = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        data_url = (
            f"data:{content_type};base64,{encoded}"
        )

        payload = {
            "model": settings.openrouter_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": """
Extract ALL readable text visible in this image.

This is a cybersecurity leak-detection task.

Preserve security-sensitive strings as accurately as possible:
- email addresses
- phone numbers
- API keys
- passwords
- access tokens
- JWTs
- IP addresses
- credit/debit card numbers
- usernames
- URLs
- secret phrases

Do NOT summarize.
Do NOT classify the information.
Do NOT invent text.

Return ONLY the visible text.
Keep separate visible lines on separate lines.
""",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 1200,
            "temperature": 0,
        }

        headers = {
            "Authorization":
                f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.frontend_origin,
            "X-Title": "LeakGuard",
        }

        async with httpx.AsyncClient(
            timeout=timeout
        ) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        result = response.json()

        extracted = (
            result.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        logger.info(
            "OpenRouter Mastodon OCR extracted %s characters",
            len(extracted),
        )

        return extracted

    except httpx.HTTPError as exc:
        logger.warning(
            "OpenRouter image request failed: %s",
            exc,
        )
        return ""

    except (OSError, ValueError) as exc:
        logger.warning(
            "Mastodon image validation failed: %s",
            exc,
        )
        return ""

    except Exception:
        logger.exception(
            "OpenRouter image OCR failed"
        )
        return ""