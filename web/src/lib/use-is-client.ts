import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/**
 * `false` при SSR и гидратации, `true` после неё (и сразу — при чисто клиентском рендере).
 * Графики считают координаты через Math.sin/cos: в Node и браузере последние знаки
 * отличаются, поэтому SVG-пути рисуем только на клиенте, иначе — ошибка гидратации.
 */
export function useIsClient(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );
}
