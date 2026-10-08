from app.core.config import settings

async def explain_with_openai(analysis: dict) -> str | None:
    if not settings.openai_api_key:
        return None
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.responses.create(
            model=settings.openai_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are LeakGuard's security explanation assistant. "
                        "Explain an already-computed detection result. Never invent findings, "
                        "never expose secrets, and never claim certainty beyond the supplied data. "
                        "Return concise, actionable text."
                    ),
                },
                {"role": "user", "content": str(analysis)},
            ],
        )
        return response.output_text[:4000]
    except Exception:
        return None
