"""Portable typed JSON contracts. Personal answers are explicit, never inferred."""

from typing import Generic, Literal, TypeVar

from pydantic import TypeAdapter
from typing_extensions import Required, TypedDict


class ApplicationName(TypedDict, total=False):
    givenName: str
    middleName: str
    familyName: str
    suffix: str


class MailingAddress(TypedDict, total=False):
    line1: str
    line2: str
    city: str
    region: str
    postalCode: str
    country: str


class AlternateEmail(TypedDict, total=False):
    email: Required[str]
    confirmedOn: Required[str]
    employer: str
    requisition: str
    country: str
    permitted: bool | None


class WorkEligibility(TypedDict, total=False):
    country: Required[str]
    confirmedOn: Required[str]
    immigrationStatus: str
    authorizedToWork: bool | None
    sponsorshipNow: bool | None
    sponsorshipFuture: bool | None
    canVerifyAuthorization: bool | None
    currentlyOnOpt: bool | None
    stemOptExtensionEligible: bool | None


class ExperienceRange(TypedDict, total=False):
    specialty: Required[str]
    confirmedOn: Required[str]
    minimumYears: float | None
    maximumYears: float | None


class EmployerAnswer(TypedDict, total=False):
    employer: Required[str]
    question: Required[str]
    confirmedOn: Required[str]
    requisition: str
    country: str
    category: Literal[
        "general",
        "referral",
        "employment",
        "contractor",
        "relationship",
        "previous_application",
        "degree_category",
        "role_requirement",
    ]
    answer: str | None
    timeframe: str
    validUntil: str | None


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
    legalName: ApplicationName
    preferredNameParts: ApplicationName
    mailingAddress: MailingAddress
    alternateEmails: list[AlternateEmail]
    workEligibility: list[WorkEligibility]
    experienceRanges: list[ExperienceRange]
    employerAnswers: list[EmployerAnswer]
    sex: str
    sexConfirmedOn: str | None
    aiMatchingPreference: Literal["unknown", "opt_in", "opt_out", "ask"]
    aiMatchingConfirmedOn: str | None


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


class ApplicationRecord(TypedDict):
    id: int
    jobId: int
    resumeVersionId: int | None
    coverLetterId: int | None
    status: str
    notes: str | None
    submittedAt: str | None
    updatedAt: str


class ApplicationEvent(TypedDict):
    id: int
    applicationId: int
    kind: str
    customLabel: str | None
    sequence: int
    sequenceOverride: int | None
    occurredAt: str | None
    allDay: bool
    timezone: str | None
    durationMinutes: int | None
    modality: str | None
    platform: str | None
    platformOther: str | None
    locationOrLink: str | None
    interviewers: str | None
    result: str
    notes: str | None
    reflection: str | None
    compBase: int | None
    compBonus: int | None
    compEquityAnnual: int | None
    compSigning: int | None
    compCurrency: str | None
    totalComp: int | None
    source: str
    createdAt: str
    updatedAt: str


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
APPLICATION = TypeAdapter(ApplicationRecord)
EVENT = TypeAdapter(ApplicationEvent)
EVENTS = TypeAdapter(list[ApplicationEvent])
