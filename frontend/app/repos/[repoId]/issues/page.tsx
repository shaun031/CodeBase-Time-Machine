import { IssueList } from "@/components/repository/github-context";

export default async function IssuesPage({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  return <IssueList repoId={repoId} />;
}
