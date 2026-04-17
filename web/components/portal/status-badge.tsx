import clsx from "clsx";

const toneClasses = {
  green: "border-pine/20 bg-pine/10 text-pine",
  yellow: "border-[#AA8A24]/20 bg-[#F8E7A6] text-[#6D5613]",
  red: "border-berry/20 bg-berry/10 text-berry",
  neutral: "border-line bg-mist text-ink/70",
};

export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: keyof typeof toneClasses;
}) {
  return (
    <span
      className={clsx(
        "inline-flex w-fit items-center rounded-[8px] border px-2.5 py-1 text-xs font-semibold",
        toneClasses[tone],
      )}
    >
      {children}
    </span>
  );
}

export function statusTone(status: string): keyof typeof toneClasses {
  if (["active", "connected", "healthy", "resolved", "answered"].includes(status)) {
    return "green";
  }
  if (["pending", "warning", "trialing", "escalated"].includes(status)) {
    return "yellow";
  }
  if (["failed", "blocked", "inactive", "past_due"].includes(status)) {
    return "red";
  }
  return "neutral";
}
