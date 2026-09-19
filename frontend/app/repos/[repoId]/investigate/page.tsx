import { InvestigationWorkspace } from "@/components/repository/investigation-workspace";

export default async function InvestigatePage({
  params,
  searchParams,
}: {
  params: Promise<{ repoId: string }>;
  searchParams: Promise<{ commit?: string; file?: string; line?: string }>;
}) {
  const { repoId } = await params;
  const query = await searchParams;
  return (
    <InvestigationWorkspace
      repoId={repoId}
      initialCommit={query.commit}
      initialFile={query.file}
      initialLine={query.line}
    />
  );
}
