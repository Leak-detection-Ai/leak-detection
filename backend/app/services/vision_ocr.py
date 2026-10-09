import base64
import io
import logging

import httpx
from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

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
    """
    Download an image attachment from Mastodon and use a
    vision-capable OpenAI model to extract visible text.

    The extracted text is NOT treated as the final detection.
    It is returned to LeakGuard's deterministic analyzer.
    """

    if not settings.openai_api_key:
        logger.warning(
            "Mastodon image OCR skipped: OPENAI_API_KEY is not configured"
        )
        return ""

    if not image_url:
        return ""

    if not image_url.startswith(
        ("http://", "https://")
    ):
        return ""

    try:
        timeout = httpx.Timeout(
            connect=5.0,
            read=20.0,
            write=20.0,
            pool=20.0,
        )

        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                image_url,
                headers={
                    "User-Agent": "LeakGuard/1.1 image-analysis"
                },
            )

            response.raise_for_status()

        image_bytes = response.content

        if len(image_bytes) > MAX_IMAGE_BYTES:
            logger.warning(
                "Skipping Mastodon image OCR: image too large"
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
                "Skipping Mastodon image OCR: unsupported type %s",
                content_type,
            )
            return ""

        # Validate the downloaded file.
        image = Image.open(
            io.BytesIO(image_bytes)
        )
        image.verify()

        encoded = base64.b64encode(
            image_bytes
        ).decode("ascii")

        data_url = (
            f"data:{content_type};base64,{encoded}"
        )

        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=settings.openai_api_key
        )

        response = await client.responses.create(
            model=settings.openai_vision_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are LeakGuard's image text extraction "
                        "assistant. Extract visible text accurately. "
                        "Preserve email addresses, phone numbers, "
                        "API keys, passwords, tokens, JWTs, IP "
                        "addresses, financial numbers, usernames, "
                        "URLs and other security-sensitive strings. "
                        "Do not summarize. Do not classify. "
                        "Return only text that is visibly present. "
                        "Do not invent missing text."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Extract all readable text from "
                                "this image. Keep visible lines "
                                "on separate lines."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": data_url,
                            "detail": "high",
                        },
                    ],
                },
            ],
        )

        text = (
            response.output_text or ""
        ).strip()

        return text

    except httpx.HTTPError as exc:
        logger.warning(
            "Mastodon image download failed: %s",
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
            "Unexpected Mastodon image OCR failure"
        )
        return ""