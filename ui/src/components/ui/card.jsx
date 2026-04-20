import { cn } from "@/lib/utils";

export function Card({ className, ...props }) {
  return (
    <div className={cn("rounded-lg border border-neutral-200 bg-white", className)} {...props} />
  );
}

export function CardHeader({ className, ...props }) {
  return (
    <div
      className={cn("flex items-start justify-between p-4 border-b border-neutral-100", className)}
      {...props}
    />
  );
}

export function CardTitle({ className, ...props }) {
  return <h3 className={cn("text-sm font-semibold text-neutral-900", className)} {...props} />;
}

export function CardContent({ className, ...props }) {
  return <div className={cn("p-4 space-y-4", className)} {...props} />;
}
