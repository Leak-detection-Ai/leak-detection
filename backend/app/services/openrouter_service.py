import httpx

from app.core.config import settings


OPENROUTER_URL = (
    "https://openrouter.ai/api/v1/chat/completions"
)


def _headers() -> dict[str, str]:
    return {
        "Authorization": (
            f"Bearer {settings.openrouter_api_key}"
        ),
        "Content-Type": "application/json",
        "HTTP-Referer": settings.frontend_origin,
        "X-Title": "LeakGuard",
    }


async def explain_analysis(
    analysis: dict,
) -> str | None:

    if not settings.openrouter_api_key:
        return None

    prompt = f"""
You are LeakGuard's cybersecurity explanation assistant.

Explain the already-computed detection result below.

Rules:
- Never invent findings.
- Never expose the full value of a detected secret.
- Do not change the risk score.
- Do not change the decision.
- Be concise and actionable.
- Explain why the detected information is sensitive.
- Give practical remediation guidance.

Detection result:
{analysis}
"""

    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "max_tokens": 500,
        "temperature": 0,
    }

    try:
        timeout = httpx.Timeout(
            connect=10.0,
            read=30.0,
            write=15.0,
            pool=10.0,
        )

        async with httpx.AsyncClient(
            timeout=timeout,
        ) as client:

            response = await client.post(
                OPENROUTER_URL,
                headers=_headers(),
                json=payload,
            )

        if response.status_code >= 400:
            print(
                "OpenRouter text error:",
                response.status_code,
                response.text[:1000],
            )

            response.raise_for_status()

        data = response.json()

        choices = data.get(
            "choices",
            [],
        )

        if not choices:
            return None

        message = choices[0].get(
            "message",
            {},
        )

        text = message.get(
            "content",
            "",
        )

        if isinstance(
            text,
            list,
        ):
            text = "\n".join(
                item.get(
                    "text",
                    "",
                )
                for item in text
                if isinstance(
                    item,
                    dict,
                )
            )

        text = (
            text
            if isinstance(
                text,
                str,
            )
            else ""
        ).strip()

        return (
            text[:4000]
            if text
            else None
        )

    except Exception as exc:
        print(
            "OpenRouter explanation failed:",
            exc,
        )
        return None