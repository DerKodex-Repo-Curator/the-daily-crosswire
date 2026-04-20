export const STATUS_COLORS = {
  ready: "bg-emerald-50 text-emerald-700 border-emerald-200",
  drafted: "bg-amber-50 text-amber-700 border-amber-200",
  running: "bg-blue-50 text-blue-700 border-blue-200",
  pending: "bg-neutral-50 text-neutral-700 border-neutral-200",
  failed: "bg-red-50 text-red-700 border-red-200",
};

export function statusClasses(status) {
  return STATUS_COLORS[status] || STATUS_COLORS.pending;
}

// True iff the status indicates work is ongoing, so the UI should keep polling.
export function isActiveStatus(status) {
  return status === "running" || status === "pending";
}
