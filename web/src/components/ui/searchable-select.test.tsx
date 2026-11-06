import { useState } from "react";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { SearchableSelect, type SearchGroup } from "./searchable-select";

const groups: SearchGroup[] = [
  {
    id: "languages",
    label: "Programming Languages",
    items: [{ value: "python", label: "Python", keywords: ["CPython"] }],
  },
  {
    id: "storage",
    label: "Databases",
    items: [{ value: "postgres", label: "PostgreSQL", disabled: true }],
  },
];

function Picker() {
  const [value, setValue] = useState<string | null>(null);
  return <SearchableSelect groups={groups} value={value} onChange={setValue} label="Canonical skill" placeholder="Choose a skill" />;
}

it("matches a group and alias, selects with the keyboard, and returns focus to the trigger", async () => {
  const user = userEvent.setup();
  render(<Picker />);
  const trigger = screen.getByRole("combobox", { name: "Canonical skill" });
  await user.tab();
  await user.keyboard("{Enter}");
  expect(await screen.findByRole("dialog", { name: "Canonical skill" })).toBeVisible();
  const search = await screen.findByRole("combobox", { name: "Search options…" });
  await user.type(search, "programming CPY");
  expect(within(screen.getByRole("group", { name: "Programming Languages" })).getByRole("option", { name: "Python" })).toBeVisible();
  expect(screen.queryByRole("group", { name: "Databases" })).not.toBeInTheDocument();
  await user.keyboard("{Enter}");
  expect(trigger).toHaveTextContent("Python");
  expect(trigger).toHaveAccessibleDescription("Python");
  expect(trigger).toHaveFocus();

  await user.keyboard("{Enter}");
  await user.type(await screen.findByRole("combobox", { name: "Search options…" }), "no such skill");
  expect(screen.getByRole("status")).toHaveTextContent("No matches");
  await user.keyboard("{Escape}");
  expect(trigger).toHaveFocus();
});
