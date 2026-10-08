import re
from html import unescape
from bs4 import BeautifulSoup

PATTERNS = [
    ("EMAIL", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), 35),
    ("PHONE", re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)"), 30),
    ("API_KEY", re.compile(r"\b(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b"), 55),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), 60),
    ("CREDIT_CARD", re.compile(r"\b(?:\d[ -]*?){13,19}\b"), 55),
    ("IP_ADDRESS", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), 20),
    ("SECRET_PHRASE", re.compile(r"(?i)\b(?:password|passwd|secret|private key|access token)\s*[:=]\s*\S+"), 60),
]

def clean_html(text: str) -> str:
    return BeautifulSoup(unescape(text), "html.parser").get_text(" ", strip=True)

def analyze_content(text: str) -> dict:
    text = clean_html(text)
    findings = []
    risk = 0
    for kind, pattern, weight in PATTERNS:
        for match in pattern.finditer(text):
            evidence = match.group(0)
            masked = evidence[:2] + "***" + evidence[-2:] if len(evidence) > 6 else "***"
            severity = "CRITICAL" if weight >= 55 else "HIGH" if weight >= 30 else "MEDIUM"
            findings.append({
                "type": kind,
                "confidence": 0.96 if kind in {"EMAIL","API_KEY","JWT"} else 0.90,
                "evidence": masked,
                "severity": severity,
            })
            risk += weight
            if len(findings) >= 10:
                break
    risk = min(100, risk)
    if risk >= 81:
        severity, decision = "CRITICAL", "BLOCK"
    elif risk >= 61:
        severity, decision = "HIGH", "WARNING"
    elif risk >= 41:
        severity, decision = "MEDIUM", "ALLOW_WITH_TIP"
    elif risk >= 21:
        severity, decision = "LOW", "ALLOW_WITH_TIP"
    else:
        severity, decision = "VERY_LOW", "ALLOW"

    recommendations = []
    for f in findings:
        recommendations.append({
            "EMAIL": "Redact the email address before public posting.",
            "PHONE": "Redact the phone number and review who can view the content.",
            "API_KEY": "Revoke/rotate the exposed key immediately and remove it from the content.",
            "JWT": "Invalidate the token and remove it from public content.",
            "CREDIT_CARD": "Remove the financial number and contact the issuer if it was exposed.",
            "IP_ADDRESS": "Consider whether the IP address is necessary to disclose.",
            "SECRET_PHRASE": "Remove the secret and rotate the associated credential.",
        }[f["type"]])

    explanation = (
        f"Detected {len(findings)} sensitive-data pattern(s). "
        f"Risk score is {risk}/100 based on sensitivity and credential exposure weights."
    )
    return {
        "risk_score": risk,
        "severity": severity,
        "decision": decision,
        "confidence": round(sum(f["confidence"] for f in findings) / len(findings), 2) if findings else 0.99,
        "findings": findings,
        "recommendations": list(dict.fromkeys(recommendations)),
        "explanation": explanation,
    }
