const ZH_NOTICES: Record<string, string> = {
  "Note not attached: quote check failed.": "引用核对未通过，笔记未添加。",
  "Some turn details could not be read, so the interview plan was unchanged.": "无法读取本轮的部分内容，面试计划未更改。",
  "Some turn details could not be read, so no note or profile changes were prepared.": "无法读取本轮的部分内容，因此没有生成笔记或个人资料修改。",
  "Some turn details could not be read, so no proposals were attached.": "无法读取本轮的部分内容，因此没有附上建议。",
  "Some recap details could not be read.": "无法读取摘要中的部分内容。",
  "The artifact formatter could not read this draft, so it remains a plain-text draft.": "无法格式化这份草稿，已保留为纯文本。",
  "Proposals were omitted because their details could not be validated.": "建议的详情无法核实，因此未予展示。",
  "Some proposals were held back to stay within this session's review limit.": "为遵守本次会话的审核数量上限，部分建议未予展示。"
};

const EN_NOTICES: Record<string, string> = {
  "Note not attached: quote check failed.": "The note wasn't attached because the quote couldn't be verified.",
  "Some turn details could not be read, so the interview plan was unchanged.": "Some details from this turn couldn't be read, so the interview plan stayed the same.",
  "Some turn details could not be read, so no note or profile changes were prepared.": "Some details from this turn couldn't be read, so no note or profile changes were prepared.",
  "Some turn details could not be read, so no proposals were attached.": "Some details from this turn couldn't be read, so no proposals were attached.",
  "Some recap details could not be read.": "Some recap details couldn't be read.",
  "The artifact formatter could not read this draft, so it remains a plain-text draft.": "The formatter couldn't read this draft, so it remains in plain text.",
};

/** Translate known application notices, leaving unfamiliar or authored text intact. */
export function localizeNotice(message: string, language: string | null | undefined): string {
  if (!language?.toLowerCase().startsWith("zh")) return EN_NOTICES[message] ?? message;
  return ZH_NOTICES[message] ?? message;
}
