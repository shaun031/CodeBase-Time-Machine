import { ArchitectureEvolution } from "@/components/repository/architecture-evolution";
import { Workspace } from "@/components/repository/workspace";

export default async function ArchitectureEvolutionPage({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  return (
    <Workspace>
      <ArchitectureEvolution repoId={repoId} />
    </Workspace>
  );
}
