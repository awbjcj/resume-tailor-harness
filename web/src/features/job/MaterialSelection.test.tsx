import { fireEvent, render, screen } from "@testing-library/react";
import type { ComponentProps } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CoverLetterRow, type CoverLetterItem } from "./CoverLetterRow";
import { VersionRow } from "./VersionRow";

const mutations = vi.hoisted(() => ({
  selectResume: vi.fn(),
  deselectResume: vi.fn(),
  selectLetter: vi.fn(),
  deselectLetter: vi.fn(),
}));

vi.mock("./use-job-mutations", () => ({
  useSelectResume: () => ({ mutate: mutations.selectResume, isPending: false }),
  useDeselectResume: () => ({ mutate: mutations.deselectResume, isPending: false }),
  useSelectCoverLetter: () => ({ mutate: mutations.selectLetter, isPending: false }),
  useDeselectCoverLetter: () => ({ mutate: mutations.deselectLetter, isPending: false }),
  useRenderVersion: () => ({ mutate: vi.fn(), isPending: false }),
  useReviseVersion: () => ({ mutate: vi.fn(), isPending: false }),
  useReviseCoverLetter: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteVersions: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteCoverLetters: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock("./artifact-runs", () => ({
  useArtifactRunIndex: () => ({}),
  resumeRevisionLifecycle: () => ({ active: false, justCreated: false, run: null }),
  coverLetterRevisionLifecycle: () => ({ active: false, justCreated: false, run: null }),
  dismissArtifactRun: vi.fn(),
}));
vi.mock("./EvidencePortfolioDisclosure", () => ({ EvidencePortfolioDisclosure: () => null }));
vi.mock("./PdfPreviewDialog", () => ({ PdfPreviewDialog: () => null }));
vi.mock("./ArtifactDeleteButton", () => ({ ArtifactDeleteButton: () => null }));

type Version = ComponentProps<typeof VersionRow>["version"];
function version(overrides: Partial<Version> = {}): Version {
  return {
    id: 11, jobId: 7, round: 1, origin: "tailor", reviewScore: 91, factCheckPassed: true,
    applicationEligible: true, pdfAvailable: false, pdfPath: null,
    hasEvidencePortfolio: false, failedGates: [], revisionUnknown: true,
    critiqueJson: null, createdAt: "2026-11-02T00:00:00Z", ...overrides,
  };
}
function letter(overrides: Partial<CoverLetterItem> = {}): CoverLetterItem {
  return { id: 21, jobId: 7, factCheckPassed: true, applicationEligible: true, pdfAvailable: false, ...overrides };
}

beforeEach(() => vi.clearAllMocks());

describe("application material selection", () => {
  it("selects the exact resume row and explains that a PDF still needs rendering", () => {
    render(<VersionRow jobId={7} version={version()} appliedVersionId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Use for application" }));
    expect(mutations.selectResume).toHaveBeenCalledWith(11);
    expect(screen.getByText("PDF unavailable. Render this version before uploading.")).toBeInTheDocument();
  });

  it("blocks a failed resume before a mutation and keeps its reason visible", () => {
    render(<VersionRow jobId={7} version={version({ applicationEligible: false })} appliedVersionId={null} />);
    const choose = screen.getByRole("button", { name: "Use for application" });
    expect(choose).toBeDisabled();
    fireEvent.click(choose);
    expect(mutations.selectResume).not.toHaveBeenCalled();
    expect(screen.getByText("Fact-lock must pass before this resume can be selected for an application.")).toBeInTheDocument();
  });

  it("allows a previously selected unsafe resume to be cleared without calling it applied", () => {
    render(<VersionRow jobId={7} version={version({ applicationEligible: false })} appliedVersionId={11} />);
    const selected = screen.getByRole("button", { name: "Selected for application" });
    expect(selected).toBeEnabled();
    expect(screen.queryByText("Applied")).not.toBeInTheDocument();
    expect(screen.getByText("This selected resume failed fact-lock. Change or clear the selection before applying.")).toBeInTheDocument();
    fireEvent.click(selected);
    expect(mutations.deselectResume).toHaveBeenCalledOnce();
  });

  it("uses actual PDF availability instead of a stale saved path", () => {
    render(<VersionRow jobId={7} version={version({ pdfPath: "stale.pdf" })} appliedVersionId={11} />);
    expect(screen.queryByRole("link", { name: "Download" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Render" })).toBeInTheDocument();
    expect(screen.getByText("Selection does not submit an application.")).toBeInTheDocument();
  });

  it("applies the same safety and clearing rules to cover letters", () => {
    const view = render(<CoverLetterRow jobId={7} coverLetter={letter({ applicationEligible: false })} appliedId={null} />);
    expect(screen.getByRole("button", { name: "Use for application" })).toBeDisabled();
    expect(screen.getByText("Fact-check must pass before this cover letter can be selected for an application.")).toBeInTheDocument();
    view.rerender(<CoverLetterRow jobId={7} coverLetter={letter({ applicationEligible: false })} appliedId={21} />);
    expect(screen.getByText("This selected cover letter failed fact-check. Change or clear the selection before applying.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Selected for application" }));
    expect(mutations.deselectLetter).toHaveBeenCalledOnce();
    expect(mutations.selectLetter).not.toHaveBeenCalled();
  });

  it("allows a safe cover letter selection while making its missing PDF explicit", () => {
    render(<CoverLetterRow jobId={7} coverLetter={letter({ pdfPath: "missing.pdf" })} appliedId={null} />);
    expect(screen.getByText("PDF unavailable. Prepare or provide this cover letter before uploading.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Download" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use for application" }));
    expect(mutations.selectLetter).toHaveBeenCalledWith(21);
  });
});
