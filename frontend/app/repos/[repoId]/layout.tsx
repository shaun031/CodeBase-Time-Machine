import { Workspace } from "@/components/repository/workspace";
export default function RepositoryLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <Workspace>{children}</Workspace>;
}
