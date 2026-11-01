import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent,
} from "react";
import type { LibraryRow } from "./SkillEditorDialog";

export type SkillDropTarget = { kind: "group" | "category"; key: string };
type Gesture = {
  row: LibraryRow;
  pointerId: number;
  x: number;
  y: number;
  startX: number;
  startY: number;
  started: boolean;
};

/** Pointer capture keeps mouse, pen and touch drags on the same small handle. */
export function useSkillDrag({
  disabled,
  onDrop,
}: {
  disabled: boolean;
  onDrop: (row: LibraryRow, target: SkillDropTarget) => void;
}) {
  const gesture = useRef<Gesture | null>(null);
  const frame = useRef<number | null>(null);
  const previewRef = useRef<HTMLDivElement>(null);
  const blocked = useRef(disabled);
  const [row, setRow] = useState<LibraryRow | null>(null);
  const [target, setTarget] = useState<SkillDropTarget | null>(null);

  const reset = useCallback(() => {
    gesture.current = null;
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    setRow(null);
    setTarget(null);
  }, []);
  useEffect(() => {
    blocked.current = disabled;
  }, [disabled]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && gesture.current) {
        event.preventDefault();
        reset();
      }
    };
    window.addEventListener("keydown", escape);
    return () => {
      window.removeEventListener("keydown", escape);
      if (frame.current !== null) cancelAnimationFrame(frame.current);
      gesture.current = null;
    };
  }, [reset]);

  const locate = useCallback((x: number, y: number): SkillDropTarget | null => {
    const node = document
      .elementFromPoint(x, y)
      ?.closest<HTMLElement>(
        "[data-skill-drop-group], [data-skill-drop-category]",
      );
    if (!node) return null;
    return node.dataset.skillDropGroup
      ? { kind: "group", key: node.dataset.skillDropGroup }
      : { kind: "category", key: node.dataset.skillDropCategory! };
  }, []);
  const position = useCallback((x: number, y: number) => {
    const preview = previewRef.current;
    if (!preview) return;
    const left = Math.max(
      8,
      Math.min(x + 14, innerWidth - preview.offsetWidth - 8),
    );
    const top = Math.max(
      8,
      Math.min(y + 14, innerHeight - preview.offsetHeight - 8),
    );
    preview.style.transform = `translate3d(${left}px, ${top}px, 0)`;
  }, []);
  useLayoutEffect(() => {
    if (row && gesture.current) position(gesture.current.x, gesture.current.y);
  }, [row, position]);

  function track() {
    const current = gesture.current;
    if (!current?.started) return;
    if (blocked.current) {
      reset();
      return;
    }
    const edge = 64;
    const delta =
      current.y < edge ? -16 : current.y > innerHeight - edge ? 16 : 0;
    if (delta) window.scrollBy(0, delta);
    const next = locate(current.x, current.y);
    setTarget((previous) =>
      previous?.kind === next?.kind && previous?.key === next?.key
        ? previous
        : next,
    );
    position(current.x, current.y);
    frame.current = requestAnimationFrame(track);
  }
  function handleProps(skill: LibraryRow) {
    return {
      onPointerDown(event: PointerEvent<HTMLElement>) {
        if (
          disabled ||
          !event.isPrimary ||
          event.button !== 0 ||
          gesture.current
        )
          return;
        event.preventDefault();
        event.stopPropagation();
        event.currentTarget.setPointerCapture(event.pointerId);
        gesture.current = {
          row: skill,
          pointerId: event.pointerId,
          x: event.clientX,
          y: event.clientY,
          startX: event.clientX,
          startY: event.clientY,
          started: false,
        };
      },
      onPointerMove(event: PointerEvent<HTMLElement>) {
        const current = gesture.current;
        if (!current || current.pointerId !== event.pointerId) return;
        if (disabled) {
          reset();
          return;
        }
        current.x = event.clientX;
        current.y = event.clientY;
        if (
          !current.started &&
          Math.hypot(current.x - current.startX, current.y - current.startY) >=
            5
        ) {
          current.started = true;
          setRow(current.row);
          track();
        }
      },
      onPointerUp(event: PointerEvent<HTMLElement>) {
        const current = gesture.current;
        if (!current || current.pointerId !== event.pointerId) return;
        event.preventDefault();
        event.stopPropagation();
        const destination =
          current.started && !disabled
            ? locate(event.clientX, event.clientY)
            : null;
        reset();
        if (event.currentTarget.hasPointerCapture(event.pointerId))
          event.currentTarget.releasePointerCapture(event.pointerId);
        if (destination) onDrop(current.row, destination);
      },
      onPointerCancel(event: PointerEvent<HTMLElement>) {
        if (gesture.current?.pointerId === event.pointerId) reset();
      },
      onLostPointerCapture(event: PointerEvent<HTMLElement>) {
        if (gesture.current?.pointerId === event.pointerId) reset();
      },
      onClick(event: React.MouseEvent) {
        event.stopPropagation();
      },
    };
  }
  return { dragging: row, target, previewRef, handleProps };
}
