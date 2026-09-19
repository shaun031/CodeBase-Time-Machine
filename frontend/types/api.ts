export interface HealthResponse {
  status: "ok";
  service: "codebase-time-machine";
}
export type ServiceStatus = "ok" | "unavailable" | "not_required";
export interface SystemStatus {
  backend: "ok";
  database: ServiceStatus;
  redis: ServiceStatus;
  ollama: "ok" | "unavailable";
}
export interface ApiErrorBody {
  error: { code: string; message: string };
}
