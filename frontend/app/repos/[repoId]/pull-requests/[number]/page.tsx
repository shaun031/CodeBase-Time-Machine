import { PullRequestView } from "@/components/repository/github-context";

export default async function PullRequestPage({
  params,
}: {
  params: Promise<{ repoId: string; number: string }>;
}) {
  const { repoId, number } = await params;
  return <PullRequestView repoId={repoId} number={Number(number)} />;
}
