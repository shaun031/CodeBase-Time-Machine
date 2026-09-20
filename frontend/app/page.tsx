import Link from "next/link";
import {
  ArrowUpRight,
  Boxes,
  GitBranch,
  GitCommitHorizontal,
  History,
  MessageSquare,
  Terminal,
  Workflow,
} from "lucide-react";
import { RepositoryForm } from "@/components/repository/repository-form";
import { SystemStatus } from "@/components/layout/system-status";

const features = [
  {
    icon: GitCommitHorizontal,
    title: "Git History",
    description: "Browse commits, changed files, renames, and diffs.",
    phase: "AVAILABLE",
  },
  {
    icon: History,
    title: "Code Explorer",
    description: "Browse current source, symbols, imports, and languages.",
    phase: "AVAILABLE",
  },
  {
    icon: MessageSquare,
    title: "Engineering Context",
    description: "Connect code changes to issues and pull requests.",
    phase: "04",
  },
  {
    icon: Workflow,
    title: "Architecture",
    description: "Understand dependencies and structural evolution.",
    phase: "05 / 08",
  },
  {
    icon: Terminal,
    title: "Local AI",
    description: "Use Ollama for evidence-backed historical explanations.",
    phase: "06",
  },
];

export default function Home() {
  return (
    <div className="shell">
      <header className="header">
        <Link
          className="brand"
          href="/"
          aria-label="Codebase Time Machine home"
        >
          <span className="brand-mark">
            <History size={21} />
          </span>
          Codebase Time Machine
        </Link>
        <span className="version mono">
          v0.3 <span className="version-divider">/</span> local workspace
        </span>
      </header>
      <main id="main-content">
        <div className="workspace-label mono">
          <span className="dot online" /> CODE EXPLORER
        </div>
        <section className="intro">
          <h1>
            Every codebase
            <br />
            has a history.
          </h1>
          <p className="tagline">
            Understand not just what your code does,
            <br className="desktop-break" /> but why it became that way.
          </p>
          <p className="description">
            Analyze public GitHub repositories, inspect their history, and
            explore the structure of the current source snapshot.
          </p>
        </section>
        <RepositoryForm />
        <section
          className="capabilities"
          aria-labelledby="capabilities-heading"
        >
          <div className="section-heading">
            <h2 id="capabilities-heading" className="mono">
              THE WORKSPACE AHEAD
            </h2>
            <span>
              Available & planned <ArrowUpRight size={13} />
            </span>
          </div>
          <div className="feature-grid">
            {features.map(({ icon: Icon, title, description, phase }) => (
              <article className="feature-card" key={title}>
                <div className="feature-top">
                  <Icon size={20} strokeWidth={1.5} aria-hidden="true" />
                  <span className="mono">{phase}</span>
                </div>
                <h3>{title}</h3>
                <p>{description}</p>
              </article>
            ))}
          </div>
        </section>
        <aside className="foundation-note">
          <Boxes size={18} aria-hidden="true" />
          <p>
            <strong>History and structure, grounded in Git.</strong> Browse the
            default branch, current source files, symbols, and imports without
            executing repository code.
          </p>
        </aside>
      </main>
      <footer>
        <SystemStatus />
        <div className="footer-bottom">
          <span>
            <GitBranch size={14} aria-hidden="true" /> Built around your code’s
            history.
          </span>
          <span className="mono">LOCAL FIRST · READ ONLY</span>
        </div>
      </footer>
    </div>
  );
}
