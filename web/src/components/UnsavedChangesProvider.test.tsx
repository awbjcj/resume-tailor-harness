import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { createMemoryRouter, Link, Outlet, RouterProvider } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { useUnsavedChanges } from "@/hooks/use-unsaved-changes";
import { UnsavedChangesProvider } from "./UnsavedChangesProvider";

function Editor({ label }: { label: string }) {
  const [value, setValue] = useState("");
  useUnsavedChanges(value !== "");
  return <div><label>{label}<input value={value} onChange={(event) => setValue(event.target.value)} /></label>
    <button onClick={() => setValue("")}>Save {label}</button></div>;
}

function setup() {
  const router = createMemoryRouter([{
    element: <UnsavedChangesProvider><Outlet /></UnsavedChangesProvider>,
    children: [
      { path: "/settings/search", element: <><Editor label="Search" /><Editor label="Other editor" /><Link to="/settings/review">Review</Link></> },
      { path: "/settings/review", element: <h1>Review settings</h1> },
    ],
  }], { initialEntries: ["/settings/search"] });
  render(<RouterProvider router={router} />);
  return userEvent.setup();
}

describe("UnsavedChangesProvider", () => {
  it("keeps edits when navigation is cancelled and follows the intended link after discard", async () => {
    const user = setup();
    await user.type(screen.getByLabelText("Search"), "platform");
    await user.click(screen.getByRole("link", { name: "Review" }));
    expect(await screen.findByRole("alertdialog")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Keep editing" }));
    expect(screen.getByLabelText("Search")).toHaveValue("platform");
    await user.click(screen.getByRole("link", { name: "Review" }));
    await user.click(screen.getByRole("button", { name: "Discard and leave" }));
    expect(await screen.findByRole("heading", { name: "Review settings" })).toBeVisible();
  });

  it("keeps the guard until every independent editor is saved", async () => {
    const user = setup();
    await user.type(screen.getByLabelText("Search"), "platform");
    await user.type(screen.getByLabelText("Other editor"), "unsaved guidance");
    await user.click(screen.getByRole("button", { name: "Save Search" }));
    const unload = new Event("beforeunload", { cancelable: true });
    fireEvent(window, unload);
    expect(unload.defaultPrevented).toBe(true);
    await user.click(screen.getByRole("button", { name: "Save Other editor" }));
    const cleanUnload = new Event("beforeunload", { cancelable: true });
    fireEvent(window, cleanUnload);
    expect(cleanUnload.defaultPrevented).toBe(false);
    await user.click(screen.getByRole("link", { name: "Review" }));
    expect(await screen.findByRole("heading", { name: "Review settings" })).toBeVisible();
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });
});
