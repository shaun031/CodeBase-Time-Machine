"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
export function useSystemStatus() {
  return useQuery({
    queryKey: ["system-status"],
    queryFn: api.getSystemStatus,
    refetchInterval: 30000,
  });
}
