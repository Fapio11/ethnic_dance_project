import assert from "node:assert/strict";
import { test } from "node:test";
import { abortableDelay, createTaskScope, pollDanceJob, observeVideoFrames } from "../lib/dance-session-runtime.ts";

test("a new task invalidates the old scope and aborts its pending wait", async () => {
  const scope = createTaskScope();
  const first = scope.begin();
  const waiting = abortableDelay(60000, first.signal);
  const second = scope.begin();
  await assert.rejects(waiting, { name: "AbortError" });
  assert.equal(first.isCurrent(), false);
  assert.equal(second.isCurrent(), true);
  scope.invalidate();
  assert.equal(second.isCurrent(), false);
});

test("a response decoding after sample replacement cannot publish a stale job", async () => {
  const scope = createTaskScope();
  const old = scope.begin();
  let decode;
  let started;
  const decoding = new Promise((resolve) => { started = resolve; });
  const updates = [];
  const polling = pollDanceJob("old-job", { ...old, interval: 0, onUpdate: (state) => updates.push(state),
    fetcher: async () => ({ ok: true, json: () => { started(); return new Promise((resolve) => { decode = resolve; }); } }) });
  await decoding;
  scope.begin();
  decode({ status: "completed", metrics: { comparison: { note: "old-reference" } } });
  await polling;
  assert.deepEqual(updates, []);
});

test("polling publishes progress and preserves the requested task id when the backend omits it", async () => {
  const scope = createTaskScope();
  const states = [{ status: "processing", progress: 40 }, { status: "completed", progress: 100 }];
  const updates = [];
  await pollDanceJob("task / 2", { ...scope.begin(), interval: 0,
    onUpdate: (state) => updates.push(state), fetcher: async (url) => {
      assert.match(url, /task%20%2F%202$/);
      return { ok: true, json: async () => states.shift() };
    } });
  assert.deepEqual(updates.map((state) => [state.id, state.status]), [["task / 2", "processing"], ["task / 2", "completed"]]);
});

test("a failed progress read can reconnect the same job without creating another upload", async () => {
  const scope = createTaskScope();
  await assert.rejects(pollDanceJob("job-7", { ...scope.begin(), interval: 0, onUpdate() {},
    fetcher: async () => ({ ok: false, status: 503 }) }), /503/);
  const updates = [];
  await pollDanceJob("job-7", { ...scope.begin(), interval: 0, onUpdate: (state) => updates.push(state),
    fetcher: async () => ({ ok: true, json: async () => ({ status: "completed" }) }) });
  assert.equal(updates[0].id, "job-7");
});

test("hidden canvas has no listener or rAF; paused canvas paints on seek only", () => {
  const frames = new Map();
  let next = 0;
  globalThis.requestAnimationFrame = (callback) => { frames.set(++next, callback); return next; };
  globalThis.cancelAnimationFrame = (id) => frames.delete(id);
  const video = new EventTarget();
  video.paused = true;
  video.ended = false;
  let paints = 0;
  const hiddenCleanup = observeVideoFrames(video, () => paints++, false);
  video.dispatchEvent(new Event("play"));
  assert.equal(paints, 0);
  assert.equal(frames.size, 0);
  hiddenCleanup();
  const cleanup = observeVideoFrames(video, () => paints++, true);
  assert.equal(paints, 1);
  assert.equal(frames.size, 0);
  video.dispatchEvent(new Event("seeked"));
  assert.equal(paints, 2);
  assert.equal(frames.size, 0);
  video.paused = false;
  video.dispatchEvent(new Event("play"));
  assert.equal(frames.size, 1);
  video.paused = true;
  video.dispatchEvent(new Event("pause"));
  assert.equal(frames.size, 0);
  cleanup();
  const final = paints;
  video.dispatchEvent(new Event("seeked"));
  assert.equal(paints, final);
  delete globalThis.requestAnimationFrame;
  delete globalThis.cancelAnimationFrame;
});
