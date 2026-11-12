import { useEffect, useRef } from "react";

/**
 * Appelle fn immédiatement puis toutes les `ms` ms.
 * - Un verrou empêche deux requêtes de se chevaucher si l'API est lente.
 * - Met en pause le polling quand l'onglet est masqué (document.hidden) pour soulager la bande passante et le serveur.
 * - Déclenche un rafraîchissement immédiat au retour sur l'onglet.
 */
export default function usePolling(fn, ms, deps = []) {
  const ref = useRef(fn);

  useEffect(() => {
    ref.current = fn;
  }, [fn]);

  useEffect(() => {
    let stopped = false;
    let busy = false;

    const tick = async () => {
      // Pause intelligente lorsque l'onglet est en arrière-plan
      if (stopped || busy || (typeof document !== "undefined" && document.hidden)) return;
      busy = true;
      try {
        await ref.current();
      } catch {
        /* les erreurs sont gérées par l'appelant */
      } finally {
        busy = false;
      }
    };

    tick();
    const id = window.setInterval(tick, ms);

    const onVisibilityChange = () => {
      if (typeof document !== "undefined" && !document.hidden) {
        tick();
      }
    };

    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibilityChange);
    }

    return () => {
      stopped = true;
      window.clearInterval(id);
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibilityChange);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps]);
}
