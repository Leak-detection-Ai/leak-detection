import re
from html import unescape

from bs4 import BeautifulSoup


PATTERNS = [
    (
        "EMAIL",
        re.compile(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            re.I,
        ),
        35,
    ),

    (
        "PHONE",
        re.compile(
            r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"
        ),
        30,
    ),

    (
        "API_KEY",
        re.compile(
            r"\b(?:"
            r"sk-[A-Za-z0-9_-]{20,}"
            r"|sk_live_[A-Za-z0-9_-]{12,}"
            r"|ghp_[A-Za-z0-9]{30,}"
            r"|AKIA[0-9A-Z]{16}"
            r")\b",
            re.I,
        ),
        55,
    ),

    (
        "JWT",
        re.compile(
            r"\beyJ[A-Za-z0-9_-]+\."
            r"[A-Za-z0-9_-]+\."
            r"[A-Za-z0-9_-]+\b"
        ),
        60,
    ),

    (
        "CREDIT_CARD",
        re.compile(
            r"\b(?:\d[ -]*?){13,19}\b"
        ),
        55,
    ),

    (
        "IP_ADDRESS",
        re.compile(
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
        ),
        20,
    ),

    (
        "SECRET_PHRASE",
        re.compile(
            r"(?i)\b(?:password|passwd|secret|"
            r"private\s+key|access\s+token|api\s+key)"
            r"\s*[:=]\s*\S+"
        ),
        60,
    ),
]


# Only strip tags that are actually common HTML tags.
# This prevents OCR text such as "<Email: john@example.com"
# from being interpreted as HTML.
KNOWN_HTML_TAGS = re.compile(
    r"</?(?:"
    r"a|abbr|article|b|blockquote|br|code|div|em|"
    r"header|i|li|ol|p|pre|section|small|span|"
    r"strong|sub|sup|table|tbody|td|th|thead|tr|"
    r"u|ul"
    r")\b[^>]*>",
    re.I,
)


def clean_html(text: str) -> str:
    text = unescape(text)

    # Remove only known HTML tags.
    text = KNOWN_HTML_TAGS.sub(" ", text)

    # Decode any remaining entities safely.
    text = unescape(text)

    # Normalize OCR whitespace without destroying punctuation.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def analyze_content(text: str) -> dict:
    cleaned = clean_html(text)

    findings = []
    risk = 0

    for kind, pattern, weight in PATTERNS:
        for match in pattern.finditer(cleaned):
            evidence = match.group(0)

            if len(evidence) > 6:
                masked = (
                    evidence[:2]
                    + "***"
                    + evidence[-2:]
                )
            else:
                masked = "***"

            if weight >= 55:
                severity = "CRITICAL"
            elif weight >= 30:
                severity = "HIGH"
            else:
                severity = "MEDIUM"

            findings.append(
                {
                    "type": kind,
                    "confidence": (
                        0.96
                        if kind
                        in {
                            "EMAIL",
                            "API_KEY",
                            "JWT",
                        }
                        else 0.90
                    ),
                    "evidence": masked,
                    "severity": severity,
                }
            )

            risk += weight

            if len(findings) >= 10:
                break

        if len(findings) >= 10:
            break

    risk = min(100, risk)

    if risk >= 81:
        severity = "CRITICAL"
        decision = "BLOCK"
    elif risk >= 61:
        severity = "HIGH"
        decision = "WARNING"
    elif risk >= 41:
        severity = "MEDIUM"
        decision = "ALLOW_WITH_TIP"
    elif risk >= 21:
        severity = "LOW"
        decision = "ALLOW_WITH_TIP"
    else:
        severity = "VERY_LOW"
        decision = "ALLOW"

    recommendations = []

    recommendation_map = {
        "EMAIL": (
            "Redact the email address before public posting."
        ),
        "PHONE": (
            "Redact the phone number and review "
            "who can view the content."
        ),
        "API_KEY": (
            "Revoke/rotate the exposed key immediately "
            "and remove it from the content."
        ),
        "JWT": (
            "Invalidate the token and remove it "
            "from public content."
        ),
        "CREDIT_CARD": (
            "Remove the financial number and contact "
            "the issuer if it was exposed."
        ),
        "IP_ADDRESS": (
            "Consider whether the IP address is "
            "necessary to disclose."
        ),
        "SECRET_PHRASE": (
            "Remove the secret and rotate the "
            "associated credential."
        ),
    }

    for finding in findings:
        recommendation = recommendation_map.get(
            finding["type"]
        )

        if recommendation:
            recommendations.append(
                recommendation
            )

    explanation = (
        f"Detected {len(findings)} "
        "sensitive-data pattern(s). "
        f"Risk score is {risk}/100 based on "
        "sensitivity and credential exposure weights."
    )

    return {
        "risk_score": risk,
        "severity": severity,
        "decision": decision,
        "confidence": (
            round(
                sum(
                    f["confidence"]
                    for f in findings
                )
                / len(findings),
                2,
            )
            if findings
            else 0.99
        ),
        "findings": findings,
        "recommendations": list(
            dict.fromkeys(recommendations)
        ),
        "explanation": explanation,
    }