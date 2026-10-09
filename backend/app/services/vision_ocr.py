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
    Download a Mastodon image and use Gemini multimodal
    understanding to extract visible text.

    The extracted text is then passed to the deterministic
    LeakGuard analyzer.
    """

    if not settings.gemini_api_key:
        logger.warning(
            "Mastodon image OCR skipped: GEMINI_API_KEY is not configured"
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
                    "User-Agent":
                        "LeakGuard/1.1 image-analysis"
                },
            )

            response.raise_for_status()

        image_bytes = response.content

        if len(image_bytes) > MAX_IMAGE_BYTES:
            logger.warning(
                "Skipping Mastodon image: exceeds size limit"
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
                "Skipping Mastodon image: unsupported MIME type %s",
                content_type,
            )
            return ""

        image = Image.open(
            io.BytesIO(image_bytes)
        )

        image.verify()

        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=settings.gemini_api_key
        )

        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=content_type,
                ),
                """
Extract ALL readable text visible in this image.

This is a cybersecurity leak-detection task.

Preserve security-sensitive strings as accurately as possible,
including:
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
Do NOT classify the data.
Do NOT invent text.
Return ONLY the text visibly present in the image.
Keep separate visible lines on separate lines.
""",
            ],
        )

        extracted = (
            response.text or ""
        ).strip()

        return extracted

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
            "Gemini image OCR failed"
        )
        return ""