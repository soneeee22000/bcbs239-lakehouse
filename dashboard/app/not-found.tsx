import Link from "next/link";
import { ArrowLeft } from "lucide-react";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-16 sm:py-24 text-center space-y-4">
      <p className="text-xs uppercase tracking-wide text-[var(--color-muted-foreground)]">
        404
      </p>
      <h1 className="text-3xl font-bold tracking-tight">Page not found</h1>
      <p className="text-[var(--color-muted-foreground)] max-w-md mx-auto">
        That route doesn&apos;t exist in the bcbs239-lakehouse dashboard. Try
        the overview, scorecard, pipeline, or exposures pages from the nav.
      </p>
      <Link
        href="/"
        className="inline-flex items-center gap-1 rounded-md bg-[var(--color-primary)] text-[var(--color-primary-foreground)] px-4 py-2 text-sm font-medium"
      >
        <ArrowLeft size={14} aria-hidden="true" />
        Back to overview
      </Link>
    </div>
  );
}
