import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { it, expect, vi } from "vitest";
import { server } from "@/test/server";
import { withQueryClient } from "@/test/utils";
import i18n from "@/i18n";
import { LearningRoadmapsPage } from "./LearningRoadmapsPage";

const { generate } = vi.hoisted(() => ({ generate: vi.fn() }));
vi.mock("./use-suggestion", () => ({ useGenerateSuggestion: () => ({ generate, generating: false }) }));

const plan = { id: 7, label: "Infrastructure", status: "planned", available: true, envelope: { stale: false, suggestion: {
  kind: "domain", key: "infra", bridge: "Practice deployment", repos: [], resources: [], citations: [], project: null, generatedAt: "2026-11-08T12:00:00Z",
} } };
function show(path = "/learning-roadmaps?plan=7") { return render(<MemoryRouter initialEntries={[path]}><LearningRoadmapsPage /></MemoryRouter>, { wrapper: withQueryClient }); }
it("opens a deep-linked domain roadmap, persists progress, archives and restores it", async () => {
  let status = "planned";
  server.use(http.get("/api/learning-roadmaps", () => HttpResponse.json([{ ...plan, status }])),
    http.patch("/api/learning-roadmaps/7", async ({ request }) => { status = (await request.json() as { status: string }).status; return new HttpResponse(null, { status: 204 }); }));
  show();
  expect(await screen.findByText("Practice deployment")).toBeInTheDocument();
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Progress" }), "archived");
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Progress" })).toBeEnabled());
  expect(status).toBe("archived");
  await userEvent.click(screen.getByRole("link", { name: "Back to roadmaps" }));
  expect(await screen.findByText("All your roadmaps are archived")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "View archived roadmaps" }));
  await userEvent.click(await screen.findByRole("link", { name: "Infrastructure" }));
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Progress" }), "in_progress");
  await waitFor(() => expect(screen.getByRole("combobox", { name: "Progress" })).toBeEnabled());
  await userEvent.click(screen.getByRole("link", { name: "Back to roadmaps" }));
  expect(screen.getByRole("combobox", { name: "Filter by progress" })).toHaveValue("archived");
  await userEvent.click(screen.getByRole("button", { name: "Reset filters" }));
  expect(await screen.findByRole("link", { name: "Infrastructure" })).toBeInTheDocument();
  await userEvent.type(screen.getByRole("textbox", { name: "Search roadmaps" }), "missing");
  expect(screen.getByText("No roadmaps match these filters.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Clear search" }));
  expect(screen.getByRole("textbox", { name: "Search roadmaps" })).toHaveFocus();
  expect(screen.getByRole("link", { name: /Infrastructure/ })).toBeInTheDocument();
});
it("offers a route into Match Gap from an empty library", async () => {
  server.use(http.get("/api/learning-roadmaps", () => HttpResponse.json([])));
  show("/learning-roadmaps");
  expect(await screen.findByRole("heading", { name: "No roadmaps yet" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Explore skill gaps" })).toHaveAttribute("href", "/match-gap");
});
it("keeps unavailable targets readable without offering regeneration", async () => {
  server.use(http.get("/api/learning-roadmaps", () => HttpResponse.json([{ ...plan, available: false }])));
  show();
  expect(await screen.findByText("Practice deployment")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Regenerate" })).not.toBeInTheDocument();
});
it("keeps superseded advice and progress while linking to the current roadmap", async () => {
  const old = { ...plan, label: "K8s", status: "completed", available: false, supersededById: 8 };
  const current = { ...plan, id: 8, label: "Kubernetes", envelope: { ...plan.envelope, suggestion: { ...plan.envelope.suggestion, bridge: "Current advice" } } };
  server.use(http.get("/api/learning-roadmaps", () => HttpResponse.json([old, current])));
  show();
  expect(await screen.findByText("Practice deployment")).toBeInTheDocument();
  expect(screen.getByRole("combobox", { name: "Progress" })).toHaveValue("completed");
  expect(screen.getByText(/Another roadmap now represents this skill/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Regenerate" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("link", { name: "Open current roadmap" }));
  expect(await screen.findByText("Current advice")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Regenerate" }));
  expect(generate).toHaveBeenCalledWith("domain", "infra", 8);
});
it("explains superseded plans in Chinese", async () => {
  await i18n.changeLanguage("zh-CN");
  try {
    server.use(http.get("/api/learning-roadmaps", () => HttpResponse.json([{ ...plan, available: false, supersededById: 8 }])));
    show();
    expect(await screen.findByText(/此技能现在对应另一条学习路线/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "打开当前学习路线" })).toBeInTheDocument();
  } finally {
    await i18n.changeLanguage("en");
  }
});
it("shows recoverable read and write errors", async () => {
  server.use(http.get("/api/learning-roadmaps", () => HttpResponse.json({ error: { code: "TEST_ERROR", message: "Unavailable" } }, { status: 500 })));
  show();
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load roadmaps.");
  server.use(http.get("/api/learning-roadmaps", () => HttpResponse.json([plan])), http.patch("/api/learning-roadmaps/7", () => HttpResponse.json({ error: { code: "TEST_ERROR", message: "Unavailable" } }, { status: 500 })));
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  const detail = await screen.findByRole("region", { name: "Infrastructure" });
  await userEvent.selectOptions(within(detail).getByRole("combobox"), "completed");
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save progress.");
  expect(within(detail).getByRole("combobox")).toHaveValue("planned");
});
