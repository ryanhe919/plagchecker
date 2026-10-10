import type { AnalysisResult, HistoryPage, JobStatus, Settings } from "./types";

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => ({}));
    if (typeof body === "object" && body !== null && "detail" in body) {
      throw new Error(String(body.detail));
    }
    throw new Error(`请求失败（HTTP ${response.status}）`);
  }
  return response.json() as Promise<T>;
}

export async function submitAnalysis(
  files: File[],
  settings: Settings,
  reference: File | null,
): Promise<JobStatus> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  if (reference) form.append("reference", reference);
  form.append("settings", JSON.stringify(settings));
  const response = await fetch("/api/v1/checker/jobs", {
    method: "POST",
    body: form,
  });
  return parseResponse<JobStatus>(response);
}

export async function getHistory(cursor?: string | null): Promise<HistoryPage> {
  const params = new URLSearchParams({ limit: "20" });
  if (cursor) params.set("cursor", cursor);
  return parseResponse<HistoryPage>(
    await fetch(`/api/v1/checker/history?${params}`),
  );
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return parseResponse<JobStatus>(await fetch(`/api/v1/checker/jobs/${jobId}`));
}

export async function getJobResult(jobId: string): Promise<AnalysisResult> {
  return parseResponse<AnalysisResult>(
    await fetch(`/api/v1/checker/jobs/${jobId}/result`),
  );
}
