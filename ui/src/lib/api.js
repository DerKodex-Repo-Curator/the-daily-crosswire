async function request(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail;
    try {
      detail = (await res.json()).detail;
    } catch {
      detail = res.statusText;
    }
    throw new Error(detail || `HTTP ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  listConfigs: () => request("/api/configs"),
  getConfig: (id) => request(`/api/configs/${id}`),
  createConfig: (data) => request("/api/configs", { method: "POST", body: data }),
  updateConfig: (id, data) => request(`/api/configs/${id}`, { method: "PATCH", body: data }),
  deleteConfig: (id) => request(`/api/configs/${id}`, { method: "DELETE" }),

  createTopic: (configId, data) =>
    request(`/api/configs/${configId}/topics`, { method: "POST", body: data }),
  updateTopic: (id, data) => request(`/api/topics/${id}`, { method: "PATCH", body: data }),
  deleteTopic: (id) => request(`/api/topics/${id}`, { method: "DELETE" }),

  createFeed: (topicId, data) =>
    request(`/api/topics/${topicId}/feeds`, { method: "POST", body: data }),
  deleteFeed: (id) => request(`/api/feeds/${id}`, { method: "DELETE" }),

  listIssues: (params = {}) => {
    const qs = new URLSearchParams();
    if (params.config_id) qs.set("config_id", params.config_id);
    if (params.from_date) qs.set("from_date", params.from_date);
    if (params.to_date) qs.set("to_date", params.to_date);
    if (params.status_filter) qs.set("status_filter", params.status_filter);
    if (params.limit) qs.set("limit", params.limit);
    const query = qs.toString();
    return request(`/api/issues${query ? `?${query}` : ""}`);
  },
  getIssue: (id) => request(`/api/issues/${id}`),
  getIssueDetails: (id) => request(`/api/issues/${id}/details`),
  getIssueLogs: (id, since) =>
    request(`/api/issues/${id}/logs${since ? `?since=${encodeURIComponent(since)}` : ""}`),
  triggerGenerate: (configId) => request(`/api/configs/${configId}/generate`, { method: "POST" }),
};
