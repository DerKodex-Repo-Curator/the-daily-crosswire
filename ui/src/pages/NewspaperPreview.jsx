import { useRef } from "react";
import { useParams, Link, Navigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Printer, ExternalLink } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { statusClasses, isActiveStatus } from "@/lib/status";

export default function NewspaperPreview() {
  const { id } = useParams();
  const iframeRef = useRef(null);

  const issueQ = useQuery({
    queryKey: ["issue", id],
    queryFn: () => api.getIssue(id),
    refetchInterval: (query) => (isActiveStatus(query.state.data?.status) ? 30000 : false),
  });

  function doPrint() {
    const iframe = iframeRef.current;
    if (!iframe || !iframe.contentWindow) return;
    iframe.contentWindow.focus();
    iframe.contentWindow.print();
  }

  if (issueQ.isLoading) {
    return <p className="text-sm text-neutral-500">Loading…</p>;
  }
  if (issueQ.isError) {
    return <p className="text-sm text-red-600">Error: {issueQ.error.message}</p>;
  }
  const issue = issueQ.data;
  if (!issue) {
    return <p className="text-sm text-red-600">Issue not found.</p>;
  }

  // Nothing to preview for non-ready issues; route to the live /details
  // dashboard, which handles running, failed, and pending.
  if (issue.status !== "ready") {
    return <Navigate to={`/issues/${id}/details`} replace />;
  }

  const ready = issue.status === "ready" && issue.html_path;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link to="/">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-3.5 w-3.5" />
              Back to newspapers
            </Button>
          </Link>
          <h1 className="text-2xl font-semibold text-neutral-900 mt-3">
            {issue.config_name || "Untitled config"} · {issue.issue_date}
          </h1>
          <p className="text-sm text-neutral-600 mt-1">
            <span className="font-mono">{issue.slug}</span>
            {" · "}status: <StatusBadge status={issue.status} />
            {" · "}
            {issue.drafts_count} drafts
            {issue.has_puzzles ? " · puzzles page" : ""}
            {issue.has_editorial ? " · editorial" : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {ready && (
            <>
              <a href={`/${issue.html_path}`} target="_blank" rel="noopener">
                <Button variant="outline" size="sm">
                  <ExternalLink className="h-3.5 w-3.5" />
                  Open raw
                </Button>
              </a>
              <Button onClick={doPrint} size="sm">
                <Printer className="h-3.5 w-3.5" />
                Print / Save as PDF
              </Button>
            </>
          )}
        </div>
      </div>

      {(issue.warnings?.length ?? 0) > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Warnings</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="text-xs text-amber-800 list-disc pl-4 space-y-1">
              {issue.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {issue.error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <p className="text-sm font-medium text-red-800">Generation failed</p>
          <pre className="mt-2 text-xs text-red-700 whitespace-pre-wrap font-mono">
            {issue.error}
          </pre>
        </div>
      )}

      {!ready && issue.status !== "failed" && (
        <div className="rounded-lg border border-dashed border-neutral-300 bg-white py-12 text-center">
          <p className="text-sm text-neutral-600">
            Status: <StatusBadge status={issue.status} />. The preview will appear once the pipeline
            finishes.
          </p>
        </div>
      )}

      {ready && (
        <div className="rounded-lg border border-neutral-200 bg-white overflow-hidden">
          <iframe
            ref={iframeRef}
            title={`Issue ${issue.slug}`}
            src={`/${issue.html_path}`}
            className="w-full h-[85vh] border-0"
          />
        </div>
      )}
    </div>
  );
}

function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${statusClasses(status)}`}
    >
      {status}
    </span>
  );
}
