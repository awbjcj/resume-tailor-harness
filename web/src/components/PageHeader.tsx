export function PageHeader({
  kicker,
  title,
  sub,
}: {
  kicker: string;
  title: string;
  sub?: string;
}) {
  return (
    <header className="grid gap-2.5 border-b pb-5 sm:gap-3 sm:pb-6">
      <div className="min-w-0">
        <p className="text-xs font-semibold uppercase tracking-[0.24em] text-primary">{kicker}</p>
        {/* Tracking and leading are size-specific: as display type grows the
            letters read too far apart and the lines too loose, so both tighten
            here while the small uppercase kicker above keeps positive tracking. */}
        <h1 className="mt-1.5 max-w-[24ch] text-balance font-heading text-[clamp(2rem,4vw,3.25rem)] font-semibold leading-[1.04] tracking-[-0.035em] text-foreground sm:mt-2">
          {title}
        </h1>
      </div>
      {sub ? (
        <p className="max-w-[68ch] text-sm leading-6 text-muted-foreground sm:text-base sm:leading-7">
          {sub}
        </p>
      ) : null}
    </header>
  );
}
