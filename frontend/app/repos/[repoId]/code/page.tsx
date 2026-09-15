import { CodeExplorer } from "@/components/repository/code-explorer";

export default async function Page({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  return <CodeExplorer key={repoId} repoId={repoId} />;
}
