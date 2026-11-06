import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SearchableSelect } from "@/components/ui/searchable-select";
import type { CategoryRow } from "../aggregate";
import { domainSearchGroups } from "./domain-search-groups";
import type { NewDomainInput } from "../use-taxonomy";

type Category = { slug: string; label: string; kind: "hard" | "soft" };

export function DomainPicker({
  categoryRows,
  categories,
  domainId,
  newDomain,
  onDomainIdChange,
  onNewDomainChange,
}: {
  categoryRows: CategoryRow[];
  categories: Category[];
  domainId: string;
  newDomain: NewDomainInput | null;
  onDomainIdChange: (value: string) => void;
  onNewDomainChange: (value: NewDomainInput | null) => void;
}) {
  const categoryItems = categories.map((category) => ({
    label: category.label,
    value: category.slug,
  }));
  return (
    <FieldGroup>
      {!newDomain && (
        <Field>
          <FieldLabel>Domain</FieldLabel>
          <SearchableSelect
            label="Domain"
            placeholder="Choose a domain"
            groups={domainSearchGroups(categoryRows)}
            value={domainId || null}
            onChange={onDomainIdChange}
          />
        </Field>
      )}
      {newDomain && (
        <>
          <Field>
            <FieldLabel htmlFor="new-domain-label">New domain label</FieldLabel>
            <Input
              id="new-domain-label"
              value={newDomain.label}
              onChange={(event) =>
                onNewDomainChange({ ...newDomain, label: event.target.value })
              }
            />
          </Field>
          <Field>
            <FieldLabel>Category</FieldLabel>
            <Select
              items={categoryItems}
              value={newDomain.category || null}
              onValueChange={(value) =>
                value && onNewDomainChange({ ...newDomain, category: value })
              }
            >
              <SelectTrigger className="w-full">
                <SelectValue>
                  {newDomain.category ? undefined : "Choose a category"}
                </SelectValue>
              </SelectTrigger>
              <SelectContent alignItemWithTrigger={false}>
                <SelectGroup>
                  {categories.map((category) => (
                    <SelectItem key={category.slug} value={category.slug}>
                      {category.label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          </Field>
        </>
      )}
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() =>
          onNewDomainChange(newDomain ? null : { label: "", category: "" })
        }
      >
        {newDomain ? "Choose existing domain" : "New domain…"}
      </Button>
    </FieldGroup>
  );
}
