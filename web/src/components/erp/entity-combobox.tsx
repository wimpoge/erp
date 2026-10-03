"use client";

import { useQuery } from "@tanstack/react-query";
import { useDeferredValue, useMemo, useState } from "react";
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
} from "@/components/ui/combobox";
import { get, Page } from "@/lib/api";

export type Option = { id: number; label: string; hint?: string; data?: unknown };

/**
 * Searchable picker backed by a paginated list endpoint (products, customers, suppliers…).
 * The server does the filtering; we only show the first matches.
 */
export function EntityCombobox<T>({
  endpoint,
  toOption,
  value,
  onChange,
  placeholder = "Search…",
  params,
  invalid,
  disabled,
  className,
}: {
  endpoint: string;
  toOption: (row: T) => Option;
  value: Option | null;
  onChange: (option: Option | null) => void;
  placeholder?: string;
  params?: Record<string, string | number | boolean>;
  invalid?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const [input, setInput] = useState("");
  const search = useDeferredValue(input);
  const { data, isFetching } = useQuery({
    queryKey: [endpoint, "picker", search, params],
    queryFn: () => get<Page<T>>(endpoint, { ...params, q: search, page_size: 12 }),
    staleTime: 60_000,
  });

  const items = useMemo(() => {
    const options = (data?.items ?? []).map(toOption);
    if (value && !options.some((o) => o.id === value.id)) options.push(value);
    return options;
    // toOption is a stable mapping per call site
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, value]);

  return (
    <Combobox
      items={items}
      value={value}
      filter={null}
      itemToStringLabel={(o: Option) => o.label}
      isItemEqualToValue={(a: Option, b: Option) => a.id === b.id}
      onValueChange={(o) => {
        onChange((o as Option | null) ?? null);
        setInput("");
      }}
      onInputValueChange={(v, { reason }) => {
        if (reason !== "item-press") setInput(v);
      }}
      disabled={disabled}
    >
      <ComboboxInput placeholder={placeholder} aria-invalid={invalid || undefined} className={className} showClear={!!value} />
      <ComboboxContent>
        <ComboboxEmpty>{isFetching ? "Searching…" : "No matches."}</ComboboxEmpty>
        <ComboboxList>
          {(o: Option) => (
            <ComboboxItem key={o.id} value={o}>
              <span className="flex min-w-0 flex-col">
                <span className="truncate">{o.label}</span>
                {o.hint && <span className="truncate text-xs text-muted-foreground">{o.hint}</span>}
              </span>
            </ComboboxItem>
          )}
        </ComboboxList>
      </ComboboxContent>
    </Combobox>
  );
}
