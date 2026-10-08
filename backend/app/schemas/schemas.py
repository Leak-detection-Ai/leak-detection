from datetime import datetime
from pydantic import BaseModel, EmailStr, Field

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: str
    email: EmailStr
    role: str
    model_config = {"from_attributes": True}

class AccountOut(BaseModel):
    id: str
    platform: str
    instance_url: str | None
    username: str
    connected: bool
    scopes: str
    last_sync: datetime | None
    model_config = {"from_attributes": True}

class Finding(BaseModel):
    type: str
    confidence: float
    evidence: str
    severity: str

class AnalyzeIn(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)

class AnalysisOut(BaseModel):
    id: str
    risk_score: int
    severity: str
    decision: str
    confidence: float
    findings: list[Finding] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    explanation: str = ""

class IncidentUpdate(BaseModel):
    status: str = Field(pattern="^(OPEN|ACKNOWLEDGED|INVESTIGATING|RESOLVED|FALSE_POSITIVE)$")
    notes: str = Field(default="", max_length=5000)
    resolution: str | None = Field(default=None, max_length=5000)

class IncidentOut(BaseModel):
    id: str
    status: str
    title: str
    notes: str = ""
    resolution: str | None = None
    created_at: datetime
    updated_at: datetime
    analysis_id: str | None = None
    risk_score: int | None = None
    severity: str | None = None
    decision: str | None = None
    confidence: float | None = None
    findings: list[Finding] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    explanation: str | None = None
    source_platform: str | None = None
    source_url: str | None = None
    source_content: str | None = None

class AlertOut(BaseModel):
    id: str
    incident_id: str | None
    severity: str
    message: str
    read: bool
    created_at: datetime
    model_config = {"from_attributes": True}
