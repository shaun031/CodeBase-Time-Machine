import { PullRequestList } from "@/components/repository/github-context";

export default async function PullRequestsPage({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  return <PullRequestList repoId={repoId} />;
}
