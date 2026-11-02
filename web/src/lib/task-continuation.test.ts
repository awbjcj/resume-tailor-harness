import { beforeEach, describe, expect, it } from "vitest";
import { consumeTaskDestination, localTaskDestination, rememberTaskDestination, taskDestination, taskDestinationForLocation, withTaskDestination } from "./task-continuation";

beforeEach(() => sessionStorage.clear());

describe("task continuation", () => {
  it.each(["https://elsewhere.test", "//elsewhere.test", "/\\elsewhere.test", "/%2felsewhere.test", "/%255celsewhere.test", "/%0aelsewhere", "/pipeline/..//elsewhere.test", "/login", "/setup", "javascript:alert(1)"])("rejects non-task destination %s", (value) => {
    expect(localTaskDestination(value)).toBeNull();
  });
  it("preserves the same Job and tab, with credentials removed", () => {
    expect(localTaskDestination("/pipeline?keywords=Data%20Engineer")).toBe("/pipeline?keywords=Data%20Engineer");
    expect(localTaskDestination("/pipeline?job=17&tab=resumes&token=secret#review")).toBe("/pipeline?job=17&tab=resumes#review");
    const path = withTaskDestination("/login", "/pipeline?job=17&tab=resumes");
    expect(taskDestination(new URLSearchParams(path.split("?")[1]))).toBe("/pipeline?job=17&tab=resumes");
  });
  it("survives an OAuth roundtrip once and rejects a forged destination", () => {
    rememberTaskDestination("/pipeline?job=17&tab=tracking");
    expect(taskDestination()).toBe("/pipeline?job=17&tab=tracking");
    expect(consumeTaskDestination(new URLSearchParams("returnTo=https://elsewhere.test"))).toBe("/pipeline?job=17&tab=tracking");
    expect(taskDestination()).toBe("/");
  });
  it("preserves the Job when authentication expires during its setup flow", () => {
    const destination = taskDestinationForLocation("/setup/documents", "?returnTo=%2Fpipeline%3Fjob%3D17%26tab%3Dresumes");
    expect(destination).toBe("/pipeline?job=17&tab=resumes");
    expect(taskDestinationForLocation("/match-gap", "?view=skills")).toBe("/match-gap?view=skills");
    expect(taskDestinationForLocation("/sources", "")).toBe("/sources");
  });
});
