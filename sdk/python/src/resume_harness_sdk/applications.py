"""Portable typed JSON contracts. Personal answers are explicit strings, never inferred."""

from typing import Generic, Literal, TypeVar

from pydantic import TypeAdapter
from typing_extensions import TypedDict


class ApplicationProfile(TypedDict, total=False):
    fullName: str
    preferredName: str
    email: str
    phone: str
    address: str
    linkedinUrl: str
    portfolioUrl: str
    expectedSalary: str
    workAuthorization: str
    sponsorshipNeeded: str
    usWorkerCategory: str
    workAuthorizationVerification: str
    availability: str
    relocation: str
    remotePreference: str
    industryExperience: str
    codingPreference: str
    technicalDomain: str
    officeAttendance: str
    atLeast18: str
    terminationHistory: str
    exportControlCitizenship: str
    plannedBoardMembership: str
    currentBoardMembership: str
    governmentEmployment: str
    referralSources: str
    previousEmployment: str
    previousApplications: str
    employerRelationships: str
    employerScreeningAnswers: str
    pronouns: str
    gender: str
    ethnicity: str
    veteranStatus: str
    disabilityStatus: str
    educationNotes: str
    experienceNotes: str
    additionalAnswers: str


class ApplicationProfileSnapshot(TypedDict):
    profile: ApplicationProfile
    revision: str


class ApplicationJob(TypedDict):
    jobId: int
    title: str | None
    company: str | None
    location: str | None
    url: str | None
    status: str


class ApplicationJobContext(ApplicationJob):
    jdText: str


class ApplicationQuestion(TypedDict):
    id: int
    question: str
    context: str
    scope: Literal["job", "profile"]
    jobId: int | None
    answer: str | None
    revision: int
    createdAt: str
    updatedAt: str


class ApplicationAttachment(TypedDict):
    id: int
    kind: Literal["resume", "cover_letter"]
    isSelected: bool
    downloadPath: str | None


class ApplicationContext(TypedDict):
    job: ApplicationJobContext
    prompt: str
    profile: ApplicationProfile
    profileRevision: str
    questions: list[ApplicationQuestion]
    attachments: list[ApplicationAttachment]
    submissionPolicy: Literal["stop_before_submit"]


class Pagination(TypedDict):
    page: int
    pageSize: int
    totalItems: int
    totalPages: int


T = TypeVar("T")


class Page(TypedDict, Generic[T]):
    data: list[T]
    pagination: Pagination


JOBS = TypeAdapter(Page[ApplicationJob])
CONTEXT = TypeAdapter(ApplicationContext)
PROFILE = TypeAdapter(ApplicationProfileSnapshot)
QUESTION = TypeAdapter(ApplicationQuestion)
QUESTIONS = TypeAdapter(Page[ApplicationQuestion])
