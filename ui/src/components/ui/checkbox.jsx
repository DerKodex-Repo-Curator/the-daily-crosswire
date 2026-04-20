import { forwardRef } from "react";
import { cn } from "@/lib/utils";

export const Checkbox = forwardRef(function Checkbox({ className, ...props }, ref) {
  return (
    <input
      ref={ref}
      type="checkbox"
      className={cn("h-4 w-4 rounded border-neutral-300 accent-neutral-900", className)}
      {...props}
    />
  );
});
