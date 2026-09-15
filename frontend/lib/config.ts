const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
export const config = { apiBaseUrl: baseUrl.replace(/\/$/, "") } as const;
