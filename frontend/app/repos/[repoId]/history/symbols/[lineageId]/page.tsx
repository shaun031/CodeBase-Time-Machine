import { SymbolHistory } from "@/components/repository/symbol-history";

export default async function SymbolHistoryPage({
  params,
}: {
  params: Promise<{ repoId: string; lineageId: string }>;
}) {
  const { repoId, lineageId } = await params;
  return <SymbolHistory repoId={repoId} lineageId={lineageId} />;
}
