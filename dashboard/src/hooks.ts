import { useEffect, useState } from "react";
import { message } from "./format";

export type Route =
  | { page: "queue" }
  | { page: "claim"; claimId: string }
  | { page: "instructions" };

export function parseRoute(hash: string): Route {
  const claimId = /^#\/claims\/([\w-]+)$/.exec(hash)?.[1];
  if (claimId) return { page: "claim", claimId };
  if (hash === "#/instructions") return { page: "instructions" };
  return { page: "queue" };
}

export function useRoute(): Route {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => {
      setHash(window.location.hash);
    };
    window.addEventListener("hashchange", onChange);
    return () => {
      window.removeEventListener("hashchange", onChange);
    };
  }, []);
  return parseRoute(hash);
}

export interface Polled<T> {
  data: T | undefined;
  error: string | undefined;
  refresh: () => void;
}

/** Load data now and again every intervalMs; 0 loads it once. */
export function usePolling<T>(
  load: () => Promise<T>,
  intervalMs: number,
): Polled<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<string>();
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let active = true;
    const refresh = () => {
      load().then(
        (value) => {
          if (!active) return;
          setData(value);
          setError(undefined);
        },
        (reason: unknown) => {
          if (active) setError(message(reason));
        },
      );
    };
    refresh();
    const timer = intervalMs ? setInterval(refresh, intervalMs) : undefined;
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [load, intervalMs, version]);

  return {
    data,
    error,
    refresh: () => {
      setVersion((v) => v + 1);
    },
  };
}
