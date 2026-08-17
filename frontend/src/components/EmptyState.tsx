interface Props {
  warnings: string[];
}

export default function EmptyState({ warnings }: Props) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-10 text-center shadow-sm">
      <p className="text-sm font-medium text-slate-700">
        No hikes matched your constraints.
      </p>
      {warnings.length > 0 && (
        <ul className="mx-auto mt-3 max-w-xl list-disc space-y-1 text-left text-xs text-amber-700">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
