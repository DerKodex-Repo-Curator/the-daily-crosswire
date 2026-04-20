import * as LabelPrimitive from "@radix-ui/react-label";
import { cn } from "@/lib/utils";

export function Label({ className, ...props }) {
  return (
    <LabelPrimitive.Root
      className={cn("text-xs font-medium text-neutral-700", className)}
      {...props}
    />
  );
}
