import { formatEur, type RwaRow } from "@/lib/data";

type RwaTableProps = {
  rows: RwaRow[];
  limit?: number;
};

export function RwaTable({ rows, limit = 10 }: RwaTableProps) {
  const visible = rows.slice(0, limit);
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
      <table className="w-full text-sm">
        <caption className="sr-only">
          Top {limit} RWA aggregation rows by total RWA EUR.
        </caption>
        <thead className="bg-[var(--color-muted)] text-left">
          <tr>
            <th scope="col" className="px-3 py-2 font-medium">
              LEI
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              Exposure type
            </th>
            <th scope="col" className="px-3 py-2 font-medium">
              As of
            </th>
            <th scope="col" className="px-3 py-2 font-medium text-right">
              Count
            </th>
            <th scope="col" className="px-3 py-2 font-medium text-right">
              Amount
            </th>
            <th scope="col" className="px-3 py-2 font-medium text-right">
              RWA
            </th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row, i) => (
            <tr
              key={`${row.lei}-${row.exposure_type}-${row.as_of_date}-${i}`}
              className="border-t border-[var(--color-border)] hover:bg-[var(--color-muted)]/40"
            >
              <td className="px-3 py-2 font-mono text-xs">{row.lei}</td>
              <td className="px-3 py-2">{row.exposure_type}</td>
              <td className="px-3 py-2 text-xs text-[var(--color-muted-foreground)]">
                {row.as_of_date}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {row.exposure_count}
              </td>
              <td className="px-3 py-2 text-right tabular-nums">
                {formatEur(row.total_amount_eur)}
              </td>
              <td className="px-3 py-2 text-right tabular-nums font-medium">
                {formatEur(row.total_rwa_eur)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
