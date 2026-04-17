export function MetricCard({
  label,
  value,
  detail,
  trend,
}: {
  label: string;
  value: string;
  detail: string;
  trend: string;
}) {
  return (
    <article className="rounded-[8px] border border-line bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <p className="text-sm font-semibold text-ink/68">{label}</p>
        <span className="rounded-[8px] bg-mist px-2.5 py-1 text-xs font-semibold text-pine">
          {trend}
        </span>
      </div>
      <p className="mt-5 font-serif text-4xl leading-none">{value}</p>
      <p className="mt-4 text-sm leading-6 text-ink/62">{detail}</p>
    </article>
  );
}
