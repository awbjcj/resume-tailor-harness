import assert from "node:assert/strict";
import test from "node:test";

import config, { partial } from "./railway.ts";

test("the production SQLite volume stays attached to one replica", async () => {
  const { resources } = await config();
  const service = resources.find((resource) => resource.type === "service");
  assert.ok(service);
  assert.deepEqual(service.volumeAttachments["resume-tailor-harness-volume"], {
    volume: "volume.resume-tailor-harness-volume",
    mountPath: "/app/data",
    volumeConfig: {
      region: "us-west2",
      sizeMB: 5000,
      allowOnlineResize: true,
      alerts: { usage: { "80": {}, "95": {}, "100": {} } },
    },
  });
  assert.deepEqual(service.deploy.multiRegionConfig, {
    "us-west2": { numReplicas: 1 },
  });
  assert.equal(service.deploy.restartPolicyMaxRetries, 3);
});

test("the partial leaves credentials and other services unmanaged", async () => {
  const definition = await config();
  assert.equal(partial, "resume-tailor-harness");
  assert.deepEqual(definition.variables, { managed: false });
  assert.deepEqual(
    definition.resources.map((resource) => resource.address),
    ["service.resume-tailor-harness"],
  );
  assert.equal(definition.resources[0].variables, undefined);
});
