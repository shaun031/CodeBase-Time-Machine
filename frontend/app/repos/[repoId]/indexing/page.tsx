import { Indexing } from "@/components/repository/indexing";
export default async function Page({
  params,
  searchParams,
}: {
  params: Promise<{ repoId: string }>;
  searchParams: Promise<{ job?: string | string[] }>;
}) {
  const { repoId } = await params;
  const { job } = await searchParams;
  return (
    <Indexing
      key={`${repoId}:${job}`}
      repoId={repoId}
      jobId={typeof job === "string" ? job : null}
    />
  );
}
