import { Architecture } from "@/components/repository/architecture";

export default async function ArchitecturePage({
  params,
  searchParams,
}: {
  params: Promise<{ repoId: string }>;
  searchParams: Promise<{ file?: string }>;
}) {
  const { repoId } = await params;
  const { file } = await searchParams;
  return <Architecture repoId={repoId} initialFileId={file} />;
}
