import Link from "next/link";
import { History } from "lucide-react";
import { errorMessage } from "@/lib/api";

export function Workspace({ children }: { children: React.ReactNode }) {
  return (
    <div className="shell">
      <header className="header">
        <Link className="brand" href="/">
          <span className="brand-mark">
            <History size={21} />
          </span>
          Codebase Time Machine
        </Link>
        <span className="mono version">CODECHRONICLE WORKSPACE</span>
      </header>
      <main className="history-main">{children}</main>
    </div>
  );
}
export function QueryError({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <div className="error-panel" role="alert">
      <p>{errorMessage(error)}</p>
      {retry && <button onClick={retry}>Try again</button>}
      <Link href="/">Back Home</Link>
    </div>
  );
}
