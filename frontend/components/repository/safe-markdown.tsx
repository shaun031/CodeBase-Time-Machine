import type { ReactNode } from "react";

function inline(value: string): ReactNode[] {
  return value
    .split(/(`[^`]*`)/g)
    .map((part, index) =>
      part.startsWith("`") && part.endsWith("`") ? (
        <code key={index}>{part.slice(1, -1)}</code>
      ) : (
        <span key={index}>{part}</span>
      ),
    );
}

export function SafeMarkdown({ value }: { value: string | null }) {
  if (!value?.trim()) return <p className="muted">No description provided.</p>;
  return <div className="safe-markdown">{markdownLines(value)}</div>;
}

function markdownLines(value: string): ReactNode[] {
  const lines = value.split(/\r\n|\n|\r/);
  let inCode = false;
  const nodes: ReactNode[] = [];
  lines.forEach((line, index) => {
    if (line.startsWith("```")) {
      inCode = !inCode;
      return;
    }
    if (inCode) {
      nodes.push(<pre key={index}>{line || " "}</pre>);
      return;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      nodes.push(<h3 key={index}>{inline(heading[2])}</h3>);
    } else if (/^[-*]\s+/.test(line)) {
      nodes.push(<p key={index}>• {inline(line.replace(/^[-*]\s+/, ""))}</p>);
    } else if (line.startsWith(">")) {
      nodes.push(
        <blockquote key={index}>{inline(line.slice(1).trim())}</blockquote>,
      );
    } else {
      nodes.push(line ? <p key={index}>{inline(line)}</p> : <br key={index} />);
    }
  });
  return nodes;
}
