import { useEffect, useRef } from "react";

/** Appelle fn immédiatement puis toutes les `ms` ms ; fn peut changer sans relancer le timer. */
export default function usePolling(fn, ms, deps = []) {
  const ref = useRef(fn);
  ref.current = fn;
  useEffect(() => {
    let stop = false;
    const tick = () => { if (!stop) ref.current(); };
    tick();
    const id = setInterval(tick, ms);
    return () => { stop = true; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps]);
}
