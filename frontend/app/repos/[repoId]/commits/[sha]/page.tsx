import { CommitView } from "@/components/repository/commit-detail";
export default async function Page({
  params,
}: {
  params: Promise<{ repoId: string; sha: string }>;
}) {
  const { repoId, sha } = await params;
  return <CommitView key={sha} repoId={repoId} sha={sha} />;
}
