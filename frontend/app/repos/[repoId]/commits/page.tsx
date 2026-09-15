import { CommitList } from "@/components/repository/commits";
export default async function Page({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  return <CommitList key={repoId} repoId={repoId} />;
}
