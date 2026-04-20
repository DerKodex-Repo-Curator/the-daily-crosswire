import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { WEEKDAY_LABELS } from "@/lib/schedule";
import { cn } from "@/lib/utils";

export function ScheduleFields({ value, onChange }) {
  const { schedule_kind, frequency_days, weekdays, run_hour } = value;

  function set(patch) {
    onChange({ ...value, ...patch });
  }

  function toggleDay(idx) {
    const current = weekdays ?? [];
    const next = current.includes(idx)
      ? current.filter((d) => d !== idx)
      : [...current, idx].sort((a, b) => a - b);
    set({ weekdays: next });
  }

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label>Schedule</Label>
        <div className="flex gap-2">
          <ModeButton
            active={schedule_kind === "interval"}
            onClick={() =>
              set({
                schedule_kind: "interval",
                weekdays: null,
                frequency_days: frequency_days ?? 1,
              })
            }
          >
            Every N days
          </ModeButton>
          <ModeButton
            active={schedule_kind === "weekdays"}
            onClick={() =>
              set({
                schedule_kind: "weekdays",
                frequency_days: null,
                weekdays: weekdays && weekdays.length ? weekdays : [0, 2, 4],
              })
            }
          >
            Specific weekdays
          </ModeButton>
        </div>
      </div>

      {schedule_kind === "interval" ? (
        <div className="space-y-1.5">
          <Label htmlFor="freq">Frequency (days)</Label>
          <Input
            id="freq"
            type="number"
            min={1}
            max={365}
            value={frequency_days ?? 1}
            onChange={(e) => set({ frequency_days: parseInt(e.target.value, 10) || 1 })}
          />
          <p className="text-xs text-neutral-500">1 = daily. 3 = every three days. 7 = weekly.</p>
        </div>
      ) : (
        <div className="space-y-1.5">
          <Label>Days of the week</Label>
          <div className="flex flex-wrap gap-2">
            {WEEKDAY_LABELS.map((label, idx) => {
              const active = (weekdays ?? []).includes(idx);
              return (
                <button
                  key={label}
                  type="button"
                  aria-pressed={active}
                  onClick={() => toggleDay(idx)}
                  className={cn(
                    "px-3 h-9 rounded-md border text-sm font-medium transition-colors",
                    active
                      ? "bg-neutral-900 text-white border-neutral-900"
                      : "bg-white text-neutral-700 border-neutral-300 hover:bg-neutral-50",
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <p className="text-xs text-neutral-500">
            Pick any combination. The lookback window uses the gap since the previous run, not a
            fixed number.
          </p>
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="hour">Run at (hour, UTC)</Label>
        <Input
          id="hour"
          type="number"
          min={0}
          max={23}
          value={run_hour ?? 6}
          onChange={(e) =>
            set({ run_hour: Math.max(0, Math.min(23, parseInt(e.target.value, 10) || 0)) })
          }
          className="max-w-24"
        />
        <p className="text-xs text-muted-foreground">
          0–23 in UTC. Applies to both interval and weekday schedules.
        </p>
      </div>
    </div>
  );
}

function ModeButton({ active, onClick, children }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        "flex-1 h-9 px-3 rounded-md border text-sm font-medium transition-colors",
        active
          ? "bg-neutral-900 text-white border-neutral-900"
          : "bg-white text-neutral-700 border-neutral-300 hover:bg-neutral-50",
      )}
    >
      {children}
    </button>
  );
}
