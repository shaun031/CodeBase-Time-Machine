import { Archaeology } from "@/components/repository/archaeology";
import { Workspace } from "@/components/repository/workspace";

export default async function ArchaeologyPage({
  params,
  searchParams,
}: {
  params: Promise<{ repoId: string }>;
  searchParams: Promise<{ lineage_id?: string }>;
}) {
  const { repoId } = await params;
  const { lineage_id } = await searchParams;
  return (
    <Workspace>
      <Archaeology repoId={repoId} initialLineageId={lineage_id} />
    </Workspace>
  );
}
