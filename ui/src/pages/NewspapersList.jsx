import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, ExternalLink, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { statusClasses, isActiveStatus } from "@/lib/status";

export default function NewspapersList() {
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [configFilter, setConfigFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const configsQ = useQuery({ queryKey: ["configs"], queryFn: api.listConfigs });
  const issuesQ = useQuery({
    queryKey: ["issues", { fromDate, toDate, configFilter, statusFilter }],
    queryFn: () =>
      api.listIssues({
        config_id: configFilter || undefined,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
        status_filter: statusFilter || undefined,
      }),
    // Only poll while at least one issue is in-flight.
    refetchInterval: (query) => {
      const rows = query.state.data ?? [];
      return rows.some((r) => isActiveStatus(r.status)) ? 30000 : false;
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-900">Newspapers</h1>
          <p className="text-sm text-neutral-600 mt-1">
            Past issues across every config. Click a row to preview.
          </p>
        </div>
      </div>

      <div className="rounded-lg border border-neutral-200 bg-white p-4">
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <div className="space-y-1">
            <Label>From</Label>
            <Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>To</Label>
            <Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Config</Label>
            <select
              className="h-9 w-full rounded-md border border-neutral-300 bg-white px-3 text-sm"
              value={configFilter}
              onChange={(e) => setConfigFilter(e.target.value)}
            >
              <option value="">Any</option>
              {(configsQ.data ?? []).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label>Status</Label>
            <select
              className="h-9 w-full rounded-md border border-neutral-300 bg-white px-3 text-sm"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">Any</option>
              <option value="ready">Ready</option>
              <option value="drafted">Drafted</option>
              <option value="running">Running</option>
              <option value="pending">Pending</option>
              <option value="failed">Failed</option>
            </select>
          </div>
        </div>
      </div>

      {issuesQ.isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {issuesQ.isError && <p className="text-sm text-red-600">Error: {issuesQ.error.message}</p>}

      {issuesQ.data && issuesQ.data.length === 0 && (
        <div className="rounded-lg border border-dashed border-neutral-300 bg-white py-12 text-center">
          <p className="text-sm text-neutral-600">
            No issues match those filters.{" "}
            <Link to="/configs" className="underline">
              Pick a config
            </Link>{" "}
            and hit Generate to create one.
          </p>
        </div>
      )}

      {issuesQ.data && issuesQ.data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-left text-xs uppercase tracking-wide text-neutral-500">
              <tr>
                <th className="px-4 py-3 font-medium">Date</th>
                <th className="px-4 py-3 font-medium">Config</th>
                <th className="px-4 py-3 font-medium">Slug</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100">
              {issuesQ.data.map((it) => (
                <tr key={it.id} className="hover:bg-neutral-50">
                  <td className="px-4 py-3 font-medium text-neutral-900">{it.issue_date}</td>
                  <td className="px-4 py-3 text-neutral-700">{it.config_name ?? "-"}</td>
                  <td className="px-4 py-3 text-neutral-500 font-mono text-xs">{it.slug}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${statusClasses(it.status)}`}
                    >
                      {it.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right space-x-1">
                    <Link to={`/issues/${it.id}`}>
                      <Button variant="ghost" size="sm">
                        <FileText className="h-3.5 w-3.5" />
                        Open
                      </Button>
                    </Link>
                    {(it.status === "ready" || it.status === "drafted") && (
                      <Link to={`/issues/${it.id}/details`}>
                        <Button variant="ghost" size="sm">
                          <BarChart3 className="h-3.5 w-3.5" />
                          Details
                        </Button>
                      </Link>
                    )}
                    {it.status === "ready" && it.html_path && (
                      <a href={`/${it.html_path}`} target="_blank" rel="noopener">
                        <Button variant="ghost" size="sm">
                          <ExternalLink className="h-3.5 w-3.5" />
                          Raw
                        </Button>
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
