import { describe, expect, it } from "vitest";

import { extractSseEvents, parseSseEvent } from "./client";

describe("parseSseEvent", () => {
  it("parses a data line into an event", () => {
    const block = 'event: token\ndata: {"type":"token","text":"你好"}\n';
    expect(parseSseEvent(block)).toEqual({ type: "token", text: "你好" });
  });

  it("returns null for blocks without a data line", () => {
    expect(parseSseEvent("event: ping\n")).toBeNull();
  });

  it("returns null for invalid JSON instead of throwing", () => {
    expect(parseSseEvent('event: token\ndata: {not json}\n')).toBeNull();
  });
});

describe("extractSseEvents", () => {
  it("emits complete events and keeps a trailing partial block", () => {
    const buffer =
      'event: status\ndata: {"type":"status"}\n\n' +
      'event: token\ndata: {"type":"token","text":"a"}\n\n' +
      'event: token\ndata: {"type":"toke';
    const { events, rest } = extractSseEvents(buffer);

    expect(events).toHaveLength(2);
    expect(events[0]).toEqual({ type: "status" });
    expect(events[1]).toEqual({ type: "token", text: "a" });
    expect(rest).toContain('{"type":"toke');
  });

  it("drops malformed blocks without interrupting the rest", () => {
    const buffer =
      'event: token\ndata: {bad}\n\n' +
      'event: token\ndata: {"type":"token","text":"ok"}\n\n';
    const { events, rest } = extractSseEvents(buffer);

    expect(events).toEqual([{ type: "token", text: "ok" }]);
    expect(rest).toBe("");
  });
});
