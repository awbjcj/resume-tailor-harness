import { useState, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { RedoDialog } from "./RedoDialog";
import { changeLanguage } from "@/i18n";

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

function setup(props: Partial<React.ComponentProps<typeof RedoDialog>> = {}) {
  const onLaunch = vi.fn().mockResolvedValue(true);
  render(
    <RedoDialog
      open
      jobIds={[1, 2, 3]}
      initialStages={["tailor"]}
      onOpenChange={() => {}}
      onLaunch={onLaunch}
      {...props}
    />,
    { wrapper },
  );
  return { onLaunch };
}

describe("RedoDialog", () => {
  it("states the exact job count in the confirm button", () => {
    setup();
    expect(
      screen.getByRole("button", { name: "Redo 3 jobs" }),
    ).toBeInTheDocument();
  });

  it("pre-ticks the stages it was opened with", () => {
    setup();
    expect(screen.getByRole("checkbox", { name: /re-tailor resume/i })).toBeChecked();
    expect(
      screen.getByRole("checkbox", { name: /re-pull job description/i }),
    ).not.toBeChecked();
  });

  it("pre-ticks re-extract when re-pull is ticked", async () => {
    const user = userEvent.setup();
    setup({ initialStages: [] });

    await user.click(screen.getByRole("checkbox", { name: /re-pull job description/i }));

    expect(
      screen.getByRole("checkbox", { name: /re-extract criteria/i }),
    ).toBeChecked();
  });

  it("lets you untick the auto-ticked re-extract", async () => {
    const user = userEvent.setup();
    setup({ initialStages: [] });

    await user.click(screen.getByRole("checkbox", { name: /re-pull job description/i }));
    await user.click(screen.getByRole("checkbox", { name: /re-extract criteria/i }));

    expect(
      screen.getByRole("checkbox", { name: /re-extract criteria/i }),
    ).not.toBeChecked();
  });

  it("launches with the ticked stages in pipeline order", async () => {
    const user = userEvent.setup();
    const { onLaunch } = setup({ initialStages: ["tailor"] });

    await user.click(screen.getByRole("checkbox", { name: /re-render pdf/i }));
    await user.click(screen.getByRole("button", { name: "Redo 3 jobs" }));

    expect(onLaunch).toHaveBeenCalledWith({
      jobIds: [1, 2, 3], stages: ["tailor", "render"], deep: false, removePreviousVersions: false,
    });
  });

  it("clears cleanup from the request when the user switches to Render alone", async () => {
    const user = userEvent.setup();
    const { onLaunch } = setup({ initialStages: ["tailor", "render"] });
    await user.click(screen.getByRole("checkbox", { name: "Delete older generated versions" }));
    await user.click(screen.getByRole("checkbox", { name: "Re-tailor resume" }));
    expect(screen.queryByRole("checkbox", { name: "Delete older generated versions" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Redo 3 jobs" }));

    expect(onLaunch).toHaveBeenCalledWith({
      jobIds: [1, 2, 3], stages: ["render"], deep: false, removePreviousVersions: false,
    });
  });

  it("clears the removal opt-in when the tailor stage is turned off and back on", async () => {
    const user = userEvent.setup();
    setup();
    await user.click(screen.getByRole("checkbox", { name: "Delete older generated versions" }));
    expect(screen.getByRole("button", { name: "Redo and delete older versions" })).toBeEnabled();

    const tailor = screen.getByRole("checkbox", { name: "Re-tailor resume" });
    await user.click(tailor);
    await user.click(tailor);

    expect(screen.getByRole("checkbox", { name: "Delete older generated versions" })).not.toBeChecked();
  });

  it("keeps the pending launch dialog open when Escape is pressed", async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    let finish!: (started: boolean) => void;
    const onLaunch = vi.fn(() => new Promise<boolean>((resolve) => { finish = resolve; }));
    setup({ onLaunch, onOpenChange });

    await user.click(screen.getByRole("button", { name: "Redo 3 jobs" }));
    expect(screen.getByRole("button", { name: "Starting…" })).toBeDisabled();
    await user.keyboard("{Escape}");
    expect(onOpenChange).not.toHaveBeenCalled();

    await act(() => finish(false));
    await user.keyboard("{Escape}");
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("disables launch when nothing is ticked", async () => {
    const user = userEvent.setup();
    setup({ initialStages: ["tailor"] });

    await user.click(screen.getByRole("checkbox", { name: /re-tailor resume/i }));

    expect(screen.getByRole("button", { name: /choose a stage/i })).toBeDisabled();
  });

  it("shows the deep-review switch only when re-tailor is ticked", async () => {
    const user = userEvent.setup();
    setup({ initialStages: [] });
    expect(screen.queryByRole("switch", { name: /deep review/i })).toBeNull();

    await user.click(screen.getByRole("checkbox", { name: /re-tailor resume/i }));

    expect(screen.getByRole("switch", { name: /deep review/i })).toBeInTheDocument();
  });

  it("keeps selected stages and translates the complete launch label across languages", async () => {
    await changeLanguage("zh-CN");
    const user = userEvent.setup();
    setup();
    expect(screen.getByRole("button", { name: "重做（3 个职位）" })).toBeEnabled();
    expect(screen.getByText("选择要为这 3 个职位重做的步骤。默认保留已有的简历版本。")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "删除较早生成的版本" })).not.toBeChecked();
    await user.click(screen.getByRole("checkbox", { name: /重新提取/ }));
    expect(screen.getByRole("button", { name: "重做（3 个职位）" })).toBeEnabled();
    await act(() => changeLanguage("en"));
    expect(screen.getByRole("button", { name: "Redo 3 jobs" })).toBeEnabled();
    expect(screen.getByRole("checkbox", { name: /re-extract criteria/i })).toBeChecked();
  });

  it("does not strand a stray '0 jobs' popup when the caller clears open and jobIds together (AttentionCard retry pattern)", async () => {
    const user = userEvent.setup();
    const onLaunch = vi.fn().mockResolvedValue(true);

    function Harness() {
      const [retry, setRetry] = useState<{ jobId: number } | null>({ jobId: 42 });
      return (
        <RedoDialog
          open={retry !== null}
          jobIds={retry ? [retry.jobId] : []}
          initialStages={["tailor"]}
          onOpenChange={(open) => {
            if (!open) setRetry(null);
          }}
          onLaunch={onLaunch}
        />
      );
    }
    render(<Harness />, { wrapper });

    expect(document.body.querySelector('[data-slot="dialog-content"]')).not.toBeNull();

    await user.click(screen.getByRole("button", { name: /cancel/i }));

    // The caller clears its target (jobIds -> []) in the same update that
    // closes the dialog. That must not remount the popup body mid-close: a
    // fresh "0 jobs" instance would mount already-closed, Base UI would
    // never animate it, and it would never disappear -- and its own
    // Cancel/Close would call back into an already-null target and do
    // nothing. The popup must simply close.
    expect(document.body.querySelector('[data-slot="dialog-content"]')).toBeNull();
  });
});
