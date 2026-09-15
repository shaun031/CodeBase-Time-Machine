import { Dashboard } from "@/components/repository/dashboard";
export default async function Page({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  return <Dashboard key={repoId} repoId={repoId} />;
}
