import { api, unwrap } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";

import { useLaunchRun } from "./use-launch-run";

export type RedoRequest = components["schemas"]["RedoParams"];
export type RedoStage = RedoRequest["stages"][number];

export function useRedoRun() {
  const { launch } = useLaunchRun();
  return {
    redo: (body: RedoRequest) =>
      launch("redo", () =>
        unwrap(api.POST("/api/redo", { body })),
      ),
  };
}
