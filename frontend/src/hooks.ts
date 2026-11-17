import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Job } from "./api";

export interface Loaded<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Fetch on mount and whenever *deps* change. A stale response never wins. */
export function useLoad<T>(fetcher: () => Promise<T>, deps: unknown[]): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tick, setTick] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    const call = ++latest.current;
    setLoading(true);
    fetcher()
      .then((value) => {
        if (call !== latest.current) return;
        setData(value);
        setError(null);
      })
      .catch((reason: Error) => {
        if (call === latest.current) setError(reason.message);
      })
      .finally(() => {
        if (call === latest.current) setLoading(false);
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { data, error, loading, reload: useCallback(() => setTick((n) => n + 1), []) };
}

const POLL_MS = 700;

/** Poll a job until it finishes; `onDone` fires once with the final state. */
export function useJob(jobId: string | null, onDone: (job: Job) => void): Job | null {
  const [job, setJob] = useState<Job | null>(null);
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      return;
    }
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const next = await api.job(jobId);
        if (cancelled) return;
        setJob(next);
        if (next.status === "succeeded" || next.status === "failed") {
          done.current(next);
          return;
        }
      } catch (reason) {
        if (cancelled) return;
        const failed: Job = {
          id: jobId, kind: "", label: "", status: "failed", progress: { done: 0, total: 0 },
          partial: {}, result: null, error: (reason as Error).message,
        };
        setJob(failed);
        done.current(failed);
        return;
      }
      timer = window.setTimeout(poll, POLL_MS);
    };
    poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [jobId]);

  return job;
}
