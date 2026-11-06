function normalize(value: string) {
  return value.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
}

/** Match every word across the entry and its ancestors, keeping punctuation in names such as C++. */
export function listSearch(query: string) {
  const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
  return (...fields: (string | null | undefined)[]) => {
    if (terms.length === 0) return true;
    const text = normalize(fields.join(" "));
    return terms.every((term) => text.includes(term));
  };
}
