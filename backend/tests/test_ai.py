from app.services.ai_engine import analyze_content

def test_email_detection():
    r = analyze_content("Contact alice@example.com")
    assert any(x["type"] == "EMAIL" for x in r["findings"])
    assert r["risk_score"] > 0

def test_secret_detection():
    r = analyze_content("api_key=sk-abcdefghijklmnopqrstuvwxyz123456")
    assert r["risk_score"] >= 55
