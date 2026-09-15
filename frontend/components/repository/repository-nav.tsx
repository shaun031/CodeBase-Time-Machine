import Link from "next/link";

export function RepositoryNav({
  repoId,
  active,
}: {
  repoId: string;
  active: string;
}) {
  const links = [
    ["Overview", `/repos/${repoId}`],
    ["Code", `/repos/${repoId}/code`],
    ["Architecture", `/repos/${repoId}/architecture`],
    ["Evolution", `/repos/${repoId}/architecture/evolution`],
    ["History", `/repos/${repoId}/history`],
    ["Archaeology", `/repos/${repoId}/archaeology`],
    ["Commits", `/repos/${repoId}/commits`],
    ["Pull Requests", `/repos/${repoId}/pull-requests`],
    ["Issues", `/repos/${repoId}/issues`],
    ["Ask", `/repos/${repoId}/ask`],
  ];
  return (
    <nav className="repo-nav" aria-label="Repository">
      {links.map(([label, href]) => (
        <Link
          key={label}
          className={active === label ? "active" : ""}
          href={href}
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
