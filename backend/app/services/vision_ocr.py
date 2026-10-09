import base64
import io
import logging
from urllib.parse import urlparse

import httpx
from PIL import Image

from app.core.config import settings


logger = logging.getLogger(__name__)

OPENROUTER_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)

MAX_IMAGE_BYTES = 8 * 1024 * 1024

SUPPORTED_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
}

EXTENSION_TO_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def _guess_mime_type(
    content_type: str,
    image_url: str,
) -> str:
    """
    Resolve a usable MIME type from the HTTP response first,
    then from the image URL extension.
    """

    mime = (
        (content_type or "")
        .split(";")[0]
        .strip()
        .lower()
    )

    if mime == "image/jpg":
        mime = "image/jpeg"

    if mime in SUPPORTED_MIME_TYPES:
        return mime

    path = urlparse(image_url).path.lower()

    for extension, extension_mime in EXTENSION_TO_MIME.items():
        if path.endswith(extension):
            return extension_mime

    return ""


def _prepare_image(
    image_bytes: bytes,
    original_mime: str,
) -> tuple[bytes, str]:
    """
    Validate the image and normalize it to PNG.
    PNG is reliable for screenshots and OCR-style content.
    """

    with Image.open(
        io.BytesIO(image_bytes)
    ) as image:
        image.verify()

    with Image.open(
        io.BytesIO(image_bytes)
    ) as image:
        # Handle animated/alpha images safely.
        try:
            image.seek(0)
        except Exception:
            pass

        if image.mode not in (
            "RGB",
            "RGBA",
        ):
            image = image.convert("RGBA")

        output = io.BytesIO()

        image.save(
            output,
            format="PNG",
            optimize=True,
        )

        normalized = output.getvalue()

    logger.info(
        "Mastodon image normalized: original_mime=%s original_bytes=%s png_bytes=%s",
        original_mime,
        len(image_bytes),
        len(normalized),
    )

    return normalized, "image/png"


def _extract_response_text(
    response_json: dict,
) -> str:
    """
    Normalize OpenRouter response content.
    Supports string content and multipart content.
    """

    choices = response_json.get(
        "choices",
        [],
    )

    if not choices:
        return ""

    message = choices[0].get(
        "message",
        {},
    )

    content = message.get(
        "content",
        "",
    )

    if isinstance(
        content,
        str,
    ):
        return content.strip()

    if isinstance(
        content,
        list,
    ):
        parts: list[str] = []

        for item in content:
            if not isinstance(
                item,
                dict,
            ):
                continue

            text = item.get(
                "text"
            )

            if isinstance(
                text,
                str,
            ):
                parts.append(
                    text
                )

        return "\n".join(
            parts
        ).strip()

    return ""


async def extract_text_from_image_url(
    image_url: str,
) -> str:
    """
    Download a Mastodon image and send it to OpenRouter
    for visual text extraction.

    Returns only extracted visible text.
    """

    if not settings.openrouter_api_key:
        logger.warning(
            "Image OCR skipped: OPENROUTER_API_KEY is not configured"
        )
        return ""

    if not image_url:
        logger.warning(
            "Image OCR skipped: empty image URL"
        )
        return ""

    if not image_url.startswith(
        (
            "http://",
            "https://",
        )
    ):
        logger.warning(
            "Image OCR skipped: invalid URL %s",
            image_url[:200],
        )
        return ""

    logger.info(
        "Starting Mastodon image OCR: %s",
        image_url[:300],
    )

    download_timeout = httpx.Timeout(
        connect=10.0,
        read=30.0,
        write=10.0,
        pool=10.0,
    )

    try:
        # ---------------------------------------------------------
        # STEP 1: Download image
        # ---------------------------------------------------------
        async with httpx.AsyncClient(
            timeout=download_timeout,
            follow_redirects=True,
        ) as client:
            response = await client.get(
                image_url,
                headers={
                    "User-Agent": "LeakGuard/1.2",
                    "Accept": "image/*",
                },
            )

        logger.info(
            "Mastodon image download response: status=%s content_type=%s bytes=%s",
            response.status_code,
            response.headers.get(
                "content-type",
                "",
            ),
            len(response.content),
        )

        response.raise_for_status()

        image_bytes = response.content

        if not image_bytes:
            logger.warning(
                "Mastodon image download returned empty body"
            )
            return ""

        if len(image_bytes) > MAX_IMAGE_BYTES:
            logger.warning(
                "Mastodon image too large: %s bytes",
                len(image_bytes),
            )
            return ""

        # ---------------------------------------------------------
        # STEP 2: Determine MIME
        # ---------------------------------------------------------
        mime_type = _guess_mime_type(
            response.headers.get(
                "content-type",
                "",
            ),
            image_url,
        )

        if not mime_type:
            logger.warning(
                "Could not determine image MIME type: %s",
                image_url[:200],
            )
            return ""

        # ---------------------------------------------------------
        # STEP 3: Validate + normalize image
        # ---------------------------------------------------------
        normalized_bytes, normalized_mime = (
            _prepare_image(
                image_bytes,
                mime_type,
            )
        )

        if len(normalized_bytes) > MAX_IMAGE_BYTES:
            logger.warning(
                "Normalized image too large: %s bytes",
                len(normalized_bytes),
            )
            return ""

        encoded = base64.b64encode(
            normalized_bytes
        ).decode("utf-8")

        data_url = (
            f"{normalized_mime};base64,{encoded}"
        )

        # ---------------------------------------------------------
        # STEP 4: OpenRouter multimodal request
        # ---------------------------------------------------------
        payload = {
            "model": settings.openrouter_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You are the OCR engine for "
                                "LeakGuard, a cybersecurity "
                                "leak-detection application.\n\n"
                                "Read the image carefully and "
                                "extract ALL text that is visibly "
                                "present.\n\n"
                                "Preserve exact security-sensitive "
                                "strings whenever readable, including:\n"
                                "- API keys\n"
                                "- passwords\n"
                                "- access tokens\n"
                                "- JWTs\n"
                                "- email addresses\n"
                                "- phone numbers\n"
                                "- IP addresses\n"
                                "- credit-card-like numbers\n"
                                "- usernames\n"
                                "- URLs\n"
                                "- secret phrases\n\n"
                                "IMPORTANT:\n"
                                "1. Do not summarize.\n"
                                "2. Do not explain the image.\n"
                                "3. Do not classify the content.\n"
                                "4. Do not invent missing characters.\n"
                                "5. Preserve capitalization and "
                                "punctuation as accurately as possible.\n"
                                "6. Keep separate visible lines "
                                "on separate lines.\n"
                                "7. Return ONLY the extracted "
                                "visible text."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": data_url,
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 2000,
            "temperature": 0,
        }

        headers = {
            "Authorization": (
                f"Bearer "
                f"{settings.openrouter_api_key}"
            ),
            "Content-Type": "application/json",
            "HTTP-Referer": settings.frontend_origin,
            "X-Title": "LeakGuard",
        }

        api_timeout = httpx.Timeout(
            connect=10.0,
            read=60.0,
            write=30.0,
            pool=10.0,
        )

        async with httpx.AsyncClient(
            timeout=api_timeout,
        ) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
            )

        # ---------------------------------------------------------
        # STEP 5: Log provider response
        # ---------------------------------------------------------
        logger.info(
            "OpenRouter vision response: status=%s",
            response.status_code,
        )

        if response.status_code >= 400:
            body = response.text[:1500]

            logger.error(
                "OpenRouter vision request failed: status=%s body=%s",
                response.status_code,
                body,
            )

            response.raise_for_status()

        response_json = (
            response.json()
        )

        # ---------------------------------------------------------
        # STEP 6: Extract returned text
        # ---------------------------------------------------------
        extracted = _extract_response_text(
            response_json
        )

        logger.info(
            "OpenRouter image OCR completed: extracted_chars=%s",
            len(extracted),
        )

        if not extracted:
            logger.warning(
                "OpenRouter returned no OCR text"
            )

        return extracted

    except httpx.HTTPStatusError as exc:
        logger.error(
            "OpenRouter image HTTP error: status=%s response=%s",
            exc.response.status_code,
            exc.response.text[:1500],
        )
        return ""

    except httpx.HTTPError as exc:
        logger.error(
            "Image download/OpenRouter HTTP error: %s",
            exc,
        )
        return ""

    except (OSError, ValueError) as exc:
        logger.error(
            "Mastodon image validation/processing failed: %s",
            exc,
        )
        return ""

    except Exception:
        logger.exception(
            "Unexpected Mastodon image OCR failure"
        )
        return ""