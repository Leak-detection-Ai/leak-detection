import httpx

from app.core.config import settings


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.frontend_origin,
        "X-Title": "LeakGuard",
    }


async def explain_analysis(analysis: dict) -> str | None:
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
            connect=5.0,
            read=20.0,
            write=10.0,
            pool=10.0,
        )

        async with httpx.AsyncClient(
            timeout=timeout
        ) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers=_headers(),
                json=payload,
            )
            response.raise_for_status()

        data = response.json()

        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        return text[:4000] if text else None

    except Exception:
        return None