import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { scheduleSummary } from "@/lib/schedule";

export default function ConfigsList() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["configs"],
    queryFn: api.listConfigs,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-neutral-900">Newspaper configs</h1>
          <p className="text-sm text-neutral-600 mt-1">
            Each config defines a schedule, topics, and RSS feeds the agent uses to draft a
            newspaper.
          </p>
        </div>
        <Link to="/configs/new">
          <Button>
            <Plus className="h-4 w-4" />
            New config
          </Button>
        </Link>
      </div>

      {isLoading && <p className="text-sm text-neutral-500">Loading…</p>}
      {isError && <p className="text-sm text-red-600">Error: {error.message}</p>}

      {data && data.length === 0 && (
        <div className="rounded-lg border border-dashed border-neutral-300 bg-white py-12 text-center">
          <p className="text-sm text-neutral-600">
            No configs yet. Create one to start generating newspapers.
          </p>
        </div>
      )}

      {data && data.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-neutral-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-neutral-50 text-left text-xs uppercase tracking-wide text-neutral-500">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Schedule</th>
                <th className="px-4 py-3 font-medium">Puzzles</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100">
              {data.map((c) => (
                <tr key={c.id} className="hover:bg-neutral-50">
                  <td className="px-4 py-3 font-medium text-neutral-900">{c.name}</td>
                  <td className="px-4 py-3 text-neutral-700">{scheduleSummary(c)}</td>
                  <td className="px-4 py-3 text-neutral-700">{c.include_puzzles ? "yes" : "no"}</td>
                  <td className="px-4 py-3 text-neutral-700">{c.active ? "active" : "paused"}</td>
                  <td className="px-4 py-3 text-right">
                    <Link to={`/configs/${c.id}`}>
                      <Button variant="ghost" size="sm">
                        <Pencil className="h-3.5 w-3.5" />
                        Edit
                      </Button>
                    </Link>
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
