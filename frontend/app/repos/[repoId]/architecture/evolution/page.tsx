import { ArchitectureEvolution } from "@/components/repository/architecture-evolution";

export default async function ArchitectureEvolutionPage({
  params,
}: {
  params: Promise<{ repoId: string }>;
}) {
  const { repoId } = await params;
  return <ArchitectureEvolution repoId={repoId} />;
}
