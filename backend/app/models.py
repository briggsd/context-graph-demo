"""Domain models for Software Engineering — auto-generated from ontology."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

class Person(BaseModel):
    """Entity model for Person."""

    name: str = Field(...)
    email: str | None = None
    role: str | None = None
    description: str | None = None

class Organization(BaseModel):
    """Entity model for Organization."""

    name: str = Field(...)
    description: str | None = None
    industry: str | None = None

class Location(BaseModel):
    """Entity model for Location."""

    name: str = Field(...)
    address: str | None = None
    latitude: float | None = None
    longitude: float | None = None

class Event(BaseModel):
    """Entity model for Event."""

    name: str = Field(...)
    date: datetime | None = None
    description: str | None = None

class Object(BaseModel):
    """Entity model for Object."""

    name: str = Field(...)
    description: str | None = None

class RepositoryVisibilityEnum(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    INTERNAL = "internal"

class Repository(BaseModel):
    """Entity model for Repository."""

    name: str = Field(...)
    language: str | None = None
    description: str | None = None
    visibility: RepositoryVisibilityEnum | None = None
    default_branch: str | None = "main"

class IssueStatusEnum(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    CLOSED = "closed"

class IssuePriorityEnum(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Issue(BaseModel):
    """Entity model for Issue."""

    issue_id: str = Field(...)
    title: str = Field(...)
    status: IssueStatusEnum | None = None
    priority: IssuePriorityEnum | None = None
    description: str | None = None
    created_date: datetime | None = None

class PullRequestStatusEnum(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    REVIEW = "review"
    MERGED = "merged"
    CLOSED = "closed"

class PullRequest(BaseModel):
    """Entity model for PullRequest."""

    pr_id: str = Field(...)
    title: str = Field(...)
    status: PullRequestStatusEnum | None = None
    lines_added: int | None = None
    lines_removed: int | None = None
    created_date: datetime | None = None

class DeploymentEnvironmentEnum(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"

class DeploymentStatusEnum(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"

class Deployment(BaseModel):
    """Entity model for Deployment."""

    deployment_id: str = Field(...)
    environment: DeploymentEnvironmentEnum | None = None
    status: DeploymentStatusEnum | None = None
    version: str | None = None
    date: datetime = Field(...)

class ServiceServiceTypeEnum(str, Enum):
    API = "api"
    WORKER = "worker"
    FRONTEND = "frontend"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"

class ServiceStatusEnum(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"

class Service(BaseModel):
    """Entity model for Service."""

    name: str = Field(...)
    service_type: ServiceServiceTypeEnum | None = None
    status: ServiceStatusEnum | None = None
    description: str | None = None

class IncidentSeverityEnum(str, Enum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    SEV4 = "sev4"

class IncidentStatusEnum(str, Enum):
    DETECTED = "detected"
    INVESTIGATING = "investigating"
    MITIGATING = "mitigating"
    RESOLVED = "resolved"
    POSTMORTEM = "postmortem"

class Incident(BaseModel):
    """Entity model for Incident."""

    incident_id: str = Field(...)
    title: str = Field(...)
    severity: IncidentSeverityEnum | None = None
    status: IncidentStatusEnum | None = None
    started_at: datetime | None = None
    resolved_at: datetime | None = None

