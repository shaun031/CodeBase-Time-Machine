import { AskAssistant } from "@/components/repository/ask";
import { Workspace } from "@/components/repository/workspace";

export default async function AskPage({
  params,
  searchParams,
}: {
  params: Promise<{ repoId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { repoId } = await params;
  const query = await searchParams;
  const first = (key: string) => {
    const value = query[key];
    return Array.isArray(value) ? value[0] : value;
  };
  const number = (key: string) => {
    const value = Number(first(key));
    return Number.isInteger(value) && value > 0 ? value : undefined;
  };
  return (
    <Workspace>
      <AskAssistant
        repoId={repoId}
        initial={{
          question: first("question"),
          lineage_id: first("lineage_id"),
          symbol_id: first("symbol_id"),
          file_path: first("file_path"),
          start_line: number("start_line"),
          end_line: number("end_line"),
          commit_sha: first("commit_sha"),
          pull_request_number: number("pull_request_number"),
          issue_number: number("issue_number"),
        }}
      />
    </Workspace>
  );
}
