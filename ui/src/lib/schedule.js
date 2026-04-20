export const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function formatHour(h) {
  return `${String(h).padStart(2, "0")}:00`;
}

export function scheduleSummary(config) {
  const hour = formatHour(config.run_hour ?? 6);
  if (config.schedule_kind === "weekdays") {
    if (!config.weekdays || config.weekdays.length === 0) {
      return `no days selected @ ${hour}`;
    }
    const days = [...config.weekdays]
      .sort((a, b) => a - b)
      .map((d) => WEEKDAY_LABELS[d])
      .join("/");
    return `${days} @ ${hour}`;
  }
  const n = config.frequency_days ?? 1;
  return `every ${n} day${n === 1 ? "" : "s"} @ ${hour}`;
}
