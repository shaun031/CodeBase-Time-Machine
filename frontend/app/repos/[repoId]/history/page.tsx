import { HistoryExplorer } from "@/components/repository/history";

export default async function HistoryPage({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  return <HistoryExplorer repoId={repoId} />;
}
