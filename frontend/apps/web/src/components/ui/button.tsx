import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "quiet";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  /** Shows a spinner and blocks a second press. The label should already say what is happening. */
  loading?: boolean;
};

const variants: Record<Variant, string> = {
  primary: "bg-accent text-on-accent hover:bg-accent-hover",
  secondary: "bg-surface text-ink border border-line-strong hover:bg-sunk",
  quiet: "bg-transparent text-ink hover:bg-sunk",
};

// One primary action per screen (docs/standards/ux.md section 5). The target is at least 48 px tall.
export function Button({ variant = "primary", loading = false, disabled, className = "", children, type = "button", ...rest }: Props) {
  return (
    <button
      type={type}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`t-base inline-flex min-h-12 items-center justify-center gap-2 rounded-full px-6 text-[15px] font-semibold active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-45 disabled:active:scale-100 ${variants[variant]} ${className}`}
      {...rest}
    >
      {loading && <span aria-hidden className="size-4 animate-spin rounded-full border-2 border-current border-t-transparent motion-reduce:animate-none" />}
      {children}
    </button>
  );
}
