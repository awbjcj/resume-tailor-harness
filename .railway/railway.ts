import { defineRailway, github, project, service, volume } from "railway/iac";

// Scope ownership to this service and its volume; the H-1B service has its own repo.
export const partial = "resume-tailor-harness";

export default defineRailway(() => {
  const dataVolume = volume("resume-tailor-harness-volume", {
    region: "us-west2",
    sizeMB: 5000,
    allowOnlineResize: true,
    alerts: { usage: { "80": {}, "95": {}, "100": {} } },
  });
  const resumeTailorHarness = service("resume-tailor-harness", {
    source: github("awbjcj/resume-tailor-harness", { branch: "main", checkSuites: false }),
    build: { buildEnvironment: "V3", builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    healthcheck: "/api/health",
    healthcheckTimeout: 120,
    replicas: { "us-west2": 1 },
    volumeMounts: { "/app/data": dataVolume },
    deploy: {
      ipv6EgressEnabled: true,
      // Railway defaults to ON_FAILURE and omits that default from IaC state.
      restartPolicyMaxRetries: 3,
    },
  });

  return project("resume-tailor-harness", {
    // Credentials and application settings stay in Railway, not in Git.
    variables: { managed: false },
    resources: [resumeTailorHarness],
  });
});
