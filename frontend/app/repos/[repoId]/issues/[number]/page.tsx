import { IssueView } from "@/components/repository/github-context";

export default async function IssuePage({
  params,
}: {
  params: Promise<{ repoId: string; number: string }>;
}) {
  const { repoId, number } = await params;
  return <IssueView repoId={repoId} number={Number(number)} />;
}
