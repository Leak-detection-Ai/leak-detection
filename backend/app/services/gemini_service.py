from app.core.config import settings


def _client():
    if not settings.gemini_api_key:
        return None

    from google import genai

    return genai.Client(
        api_key=settings.gemini_api_key
    )


async def explain_analysis(analysis: dict) -> str | None:
    client = _client()

    if client is None:
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

    try:
        response = client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
        )

        text = (response.text or "").strip()

        return text[:4000] if text else None

    except Exception:
        return None