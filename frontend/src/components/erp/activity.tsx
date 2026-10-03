import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { dateTimeLabel } from "@/lib/format";
import type { Activity } from "@/lib/types";

/** Audit trail of a record: who did what, when. */
export function ActivityTimeline({ items, title = "History" }: { items: Activity[]; title?: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">No activity yet.</p>
        ) : (
          <ol className="relative space-y-4 border-l pl-5">
            {[...items].reverse().map((a) => (
              <li key={a.id} className="relative">
                <span className="absolute top-1.5 -left-[25px] size-2.5 rounded-full border-2 border-background bg-primary" />
                <p className="text-sm">{a.message}</p>
                <p className="text-xs text-muted-foreground">
                  {dateTimeLabel(a.at)} · {a.user?.name ?? "Integration API"}
                </p>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
