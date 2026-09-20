import { useState } from "react";

import { useFundamentals } from "../api/hooks.js";

const DESCRIPTION_TRUNCATE = 600;

function MetaCell({ label, value }) {
  return (
    <div>
      <div className="text-xs font-mono text-ink-500 tracking-wider">
        {label}
      </div>
      <div className="mt-1 text-sm text-ink-200">{value}</div>
    </div>
  );
}

export default function CompanyProfile({ ticker }) {
  const { data, isLoading, error } = useFundamentals(ticker);
  const [expanded, setExpanded] = useState(false);

  if (isLoading) {
    return (
      <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-5 space-y-3">
        <div className="h-4 bg-ink-700 rounded animate-pulse w-5/6" />
        <div className="h-4 bg-ink-700 rounded animate-pulse w-4/6" />
        <div className="h-4 bg-ink-700 rounded animate-pulse w-3/6" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg bg-ink-800 border border-accent-down/40 px-5 py-4 text-sm text-accent-down">
        Failed to load company profile: {error.message}
      </div>
    );
  }

  const description = data.description ?? "";
  const tooLong = description.length > DESCRIPTION_TRUNCATE;
  const shown =
    tooLong && !expanded
      ? description.slice(0, DESCRIPTION_TRUNCATE).trimEnd() + "…"
      : description;

  const hq =
    [data.city, data.country].filter(Boolean).join(", ") || "—";
  const employeeStr =
    data.employees != null
      ? data.employees.toLocaleString("en-IN")
      : "—";

  return (
    <div className="rounded-lg bg-ink-800 border border-ink-700 px-5 py-5 space-y-5">
      {/* Description */}
      {description ? (
        <div>
          <p className="text-ink-200 leading-relaxed text-[15px]">
            {shown}
          </p>
          {tooLong && (
            <button
              type="button"
              onClick={() => setExpanded((e) => !e)}
              className="mt-2 text-xs font-mono tracking-wider text-accent hover:underline"
            >
              {expanded ? "SHOW LESS" : "READ MORE"}
            </button>
          )}
        </div>
      ) : (
        <p className="text-sm text-ink-400">No description available.</p>
      )}

      {/* Metadata row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-3 border-t border-ink-700">
        <MetaCell label="INDUSTRY"  value={data.industry ?? "—"} />
        <MetaCell label="EMPLOYEES" value={employeeStr} />
        <MetaCell label="HQ"        value={hq} />
        <MetaCell
          label="WEBSITE"
          value={
            data.website ? (
              <a
                href={data.website}
                target="_blank"
                rel="noopener noreferrer"
                className="text-accent hover:underline break-all"
              >
                {data.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}
              </a>
            ) : (
              "—"
            )
          }
        />
      </div>
    </div>
  );
}
