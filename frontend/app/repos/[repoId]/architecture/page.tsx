import { Architecture } from "@/components/repository/architecture";
import { Workspace } from "@/components/repository/workspace";

export default async function ArchitecturePage({
  params,
  searchParams,
}: {
  params: Promise<{ repoId: string }>;
  searchParams: Promise<{ file?: string }>;
}) {
  const { repoId } = await params;
  const { file } = await searchParams;
  return (
    <Workspace>
      <Architecture repoId={repoId} initialFileId={file} />
    </Workspace>
  );
}
