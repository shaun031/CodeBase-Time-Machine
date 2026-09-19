import { Archaeology } from "@/components/repository/archaeology";

export default async function ArchaeologyPage({
  params,
  searchParams,
}: {
  params: Promise<{ repoId: string }>;
  searchParams: Promise<{ lineage_id?: string }>;
}) {
  const { repoId } = await params;
  const { lineage_id } = await searchParams;
  return <Archaeology repoId={repoId} initialLineageId={lineage_id} />;
}
