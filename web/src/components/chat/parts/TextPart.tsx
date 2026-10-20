import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

const remarkPlugins = [remarkGfm, remarkBreaks];
const components: Components = {
  table: ({ children }) => (
    <div className="chat-markdown-scroll" role="region" aria-label="Table" tabIndex={0}>
      <table>{children}</table>
    </div>
  ),
  pre: ({ children }) => <pre tabIndex={0} aria-label="Code block">{children}</pre>,
};

// Tool/reasoning updates must not reparse already-rendered Markdown.
export const TextPart = memo(function TextPart({ text, caret = false }: { text: string; caret?: boolean }) {
  return (
    <div data-testid="chat-part-text" className="chat-markdown text-base leading-7">
      <ReactMarkdown remarkPlugins={remarkPlugins} components={components}>{text}</ReactMarkdown>
      {caret ? (
        <span
          aria-hidden="true"
          data-testid="chat-stream-caret"
          className="ml-0.5 inline-block h-4 w-0.5 bg-foreground align-text-bottom motion-safe:animate-pulse"
        />
      ) : null}
    </div>
  );
});
