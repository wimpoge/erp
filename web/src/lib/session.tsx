"use client";

import { useRouter } from "next/navigation";
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { api, Location, Register, User } from "./api";

type Session = {
  user: User;
  locations: Location[];
  /** The store this till sells in: a cashier's own store, or the one an admin picked. */
  location: Location | null;
  register: Register | null;
  setLocation: (id: number) => void;
  setRegister: (id: number) => void;
  logout: () => Promise<void>;
};

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession outside SessionProvider");
  return session;
}

// Which store / register this device uses is remembered per browser.
const DEVICE_KEY = "my-pos.device";

function readDevice(): { locationId?: number; registerId?: number } {
  try {
    return JSON.parse(localStorage.getItem(DEVICE_KEY) ?? "{}");
  } catch {
    return {};
  }
}

function writeDevice(value: { locationId?: number; registerId?: number }) {
  try {
    localStorage.setItem(DEVICE_KEY, JSON.stringify(value));
  } catch {}
}

export function SessionProvider({ children, fallback }: { children: ReactNode; fallback: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState<number | null>(null);
  const [registerId, setRegisterId] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([api<User>("/api/auth/me"), api<Location[]>("/api/locations")])
      .then(([me, locs]) => {
        const saved = readDevice();
        const loc = me.location ? locs.find((l) => l.id === me.location!.id) : (locs.find((l) => l.id === saved.locationId) ?? locs[0]);
        setUser(me);
        setLocations(locs);
        setLocationId(loc?.id ?? null);
        setRegisterId(loc?.registers.find((r) => r.id === saved.registerId)?.id ?? loc?.registers[0]?.id ?? null);
      })
      .catch(() => router.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`));
  }, [router]);

  const location = locations.find((l) => l.id === locationId) ?? null;
  const register = location?.registers.find((r) => r.id === registerId) ?? null;

  const chooseLocation = useCallback(
    (id: number) => {
      const loc = locations.find((l) => l.id === id);
      setLocationId(id);
      setRegisterId(loc?.registers[0]?.id ?? null);
      writeDevice({ locationId: id, registerId: loc?.registers[0]?.id });
    },
    [locations],
  );

  const chooseRegister = useCallback(
    (id: number) => {
      setRegisterId(id);
      writeDevice({ locationId: locationId ?? undefined, registerId: id });
    },
    [locationId],
  );

  const logout = useCallback(async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
    }
  }, [router]);

  if (!user) return <>{fallback}</>;
  return (
    <SessionContext.Provider
      value={{ user, locations, location, register, setLocation: chooseLocation, setRegister: chooseRegister, logout }}
    >
      {children}
    </SessionContext.Provider>
  );
}
