"""Database tables for users and future job, style, and content persistence."""

from typing import Optional

from datetime import datetime

from sqlalchemy import BigInteger, JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AIModel(Base):
    __tablename__ = "ai_models"
    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class AIModelRoute(Base):
    __tablename__ = "ai_model_routes"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class AIGatewaySettings(Base):
    __tablename__ = "ai_gateway_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class AIRequestLog(Base):
    __tablename__ = "ai_request_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    route: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    model: Mapped[str] = mapped_column(String(512), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    refresh_tokens: Mapped[list[str]] = mapped_column(JSON, default=list)
    reset_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reset_expires: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="new")
    stage: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    progress_pct: Mapped[int] = mapped_column(Integer, default=0)
    source_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    # Compatibility state keeps the public job JSON stable while its canonical
    # persistence moves out of the old status.json sidecar.
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    # Keep the original migration's ISO-string timestamp representation so
    # existing installations upgrade without an in-place type rewrite.
    created_at: Mapped[str] = mapped_column(String(50), default=lambda: datetime.utcnow().isoformat())
    updated_at: Mapped[Optional[str]] = mapped_column(String(50), nullable=True,
                                                       onupdate=lambda: datetime.utcnow().isoformat())


# Backwards-compatible import name for the existing auth/content code.
JobModel = Job


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True, index=True)
    scenes: Mapped[list] = mapped_column(JSON, default=list)
    captions: Mapped[list] = mapped_column(JSON, default=list)
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class PlanVersion(Base):
    """Immutable snapshot of a job's plan after each change (undo history)."""

    __tablename__ = "plan_versions"
    __table_args__ = (UniqueConstraint("job_id", "version", name="uq_plan_versions_job_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    parent_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # ai_generate | user_ui | chat | qc | undo | legacy
    source: Mapped[str] = mapped_column(String(32))
    operations: Mapped[list] = mapped_column(JSON, default=list)
    plan: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class RenderResult(Base):
    __tablename__ = "render_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    output_path: Mapped[str] = mapped_column(String(1000))
    format: Mapped[str] = mapped_column(String(50), default="mp4")
    duration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class QCResult(Base):
    __tablename__ = "qc_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class StyleProfileModel(Base):
    __tablename__ = "style_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    profile_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(50))


class StyleReference(Base):
    """One analyzed reference reel used to build a user's learned style."""

    __tablename__ = "style_references"
    __table_args__ = (UniqueConstraint("user_id", "digest", name="uq_style_references_user_digest"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    digest: Mapped[str] = mapped_column(String(32))
    source_file: Mapped[str] = mapped_column(String(500), default="")
    analysis: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class LearnedStyleProfile(Base):
    """A user's merged learned style profile (one row per user)."""

    __tablename__ = "learned_style_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, unique=True)
    profile: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PlanStyleSelection(Base):
    """A user's default approved visual style for newly generated plans."""

    __tablename__ = "plan_style_selections"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    style_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class PlanStyleVisibility(Base):
    """User choice to hide the built-in defaults card, not the render preset."""

    __tablename__ = "plan_style_visibility"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    default_hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class ContentRequestModel(Base):
    __tablename__ = "content_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    prompt: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(50), default="pending")
    job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[str] = mapped_column(String(50))


class StudioConversation(Base):
    """Durable chat context; projects are deliberately separate records."""

    __tablename__ = "studio_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_key: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(255), default="گفتگوی جدید")
    language: Mapped[str] = mapped_column(String(8), default="fa")
    status_voice_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class StudioMessage(Base):
    __tablename__ = "studio_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("studio_conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    agent_mode: Mapped[str] = mapped_column(String(16), default="lite", server_default="lite")
    attachments: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class StudioAttachment(Base):
    __tablename__ = "studio_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("studio_conversations.id", ondelete="CASCADE"), index=True
    )
    user_key: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(255))
    path: Mapped[str] = mapped_column(String(1000))
    mime_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class StudioProject(Base):
    __tablename__ = "studio_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("studio_conversations.id", ondelete="CASCADE"), index=True
    )
    user_key: Mapped[str] = mapped_column(String(64), index=True)
    engine: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="planning")
    external_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class StudioProjectVersion(Base):
    __tablename__ = "studio_project_versions"
    __table_args__ = (
        UniqueConstraint("project_id", "version", name="uq_studio_project_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("studio_projects.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(32))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class StudioAction(Base):
    __tablename__ = "studio_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("studio_conversations.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("studio_projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class StudioEvent(Base):
    __tablename__ = "studio_events"
    __table_args__ = (
        UniqueConstraint("conversation_id", "seq", name="uq_studio_event_seq"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("studio_conversations.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)


class StudioAgentPreference(Base):
    __tablename__ = "studio_agent_preferences"
    user_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    default_mode: Mapped[str] = mapped_column(String(16), default="lite")


class StudioAgentRun(Base):
    __tablename__ = "studio_agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("studio_conversations.id", ondelete="CASCADE"), index=True)
    user_key: Mapped[str] = mapped_column(String(64), index=True)
    message_id: Mapped[str] = mapped_column(String(64))
    agent_mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("conversation_id", "message_id", name="uq_studio_agent_message"),)


class CreditAccount(Base):
    """A person's credit balance, in weighted tokens (see app/credits.py). The balance may dip below zero: a running job is never cut."""
    __tablename__ = "credit_accounts"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    balance: Mapped[int] = mapped_column(BigInteger, default=0)
    granted_total: Mapped[int] = mapped_column(BigInteger, default=0)
    used_total: Mapped[int] = mapped_column(BigInteger, default=0)
    unlimited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class CreditLedger(Base):
    """Every change of a balance: usage (negative) of one model call, or a grant / purchase / admin change / refund (positive or negative)."""
    __tablename__ = "credit_ledger"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)            # usage | initial | grant | purchase | admin | refund
    amount: Mapped[int] = mapped_column(BigInteger)                      # signed: usage is negative
    balance_after: Mapped[int] = mapped_column(BigInteger)
    request_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)   # the ai_request_logs row
    route: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    project_kind: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    job_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    output_tokens: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    cache_tokens: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    actor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class CreditPackage(Base):
    __tablename__ = "credit_packages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    credits: Mapped[int] = mapped_column(BigInteger)
    price: Mapped[int] = mapped_column(BigInteger, default=0)            # in the currency's smallest shown unit (e.g. toman)
    currency: Mapped[str] = mapped_column(String(8), default="IRT")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)


class CreditOrder(Base):
    __tablename__ = "credit_orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    package_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    credits: Mapped[int] = mapped_column(BigInteger)
    price: Mapped[int] = mapped_column(BigInteger, default=0)
    currency: Mapped[str] = mapped_column(String(8), default="IRT")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)   # pending | paid | cancelled
    gateway: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    gateway_ref: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    paid_at: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
