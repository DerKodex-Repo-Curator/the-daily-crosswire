import { forwardRef } from "react";
import { cn } from "@/lib/utils";

const variants = {
  default: "bg-neutral-900 text-white hover:bg-neutral-800 disabled:opacity-50",
  outline: "border border-neutral-300 bg-white text-neutral-900 hover:bg-neutral-50",
  ghost: "text-neutral-700 hover:bg-neutral-100",
  destructive: "bg-red-600 text-white hover:bg-red-700",
};

const sizes = {
  default: "h-9 px-4 text-sm",
  sm: "h-8 px-3 text-xs",
  icon: "h-8 w-8",
};

export const Button = forwardRef(function Button(
  { className, variant = "default", size = "default", type = "button", ...props },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors disabled:pointer-events-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neutral-400",
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    />
  );
});
