import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { getDeliveryWsUrl, formatCurrency } from "./utils";

describe("formatCurrency", () => {
  it("formats positive numeric amount as INR currency string", () => {
    const formatted = formatCurrency(120.5);
    expect(formatted).toContain("120.50");
  });

  it("handles string amounts and fallback", () => {
    expect(formatCurrency("49.99")).toContain("49.99");
    expect(formatCurrency(0)).toContain("0.00");
  });
});

describe("getDeliveryWsUrl", () => {
  beforeEach(() => {
    vi.stubEnv("VITE_WS_URL", "");
    vi.stubEnv("VITE_API_URL", "");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("uses VITE_WS_URL directly when provided", () => {
    vi.stubEnv("VITE_WS_URL", "wss://api.dukaanly.example.com/api/v1");
    const url = getDeliveryWsUrl("del-123", "token-abc");
    expect(url).toBe("wss://api.dukaanly.example.com/api/v1/ws/deliveries/del-123?token=token-abc");
  });

  it("derives wss:// from https:// VITE_API_URL", () => {
    vi.stubEnv("VITE_API_URL", "https://api.dukaanly.example.com/api/v1");
    const url = getDeliveryWsUrl("del-123", "token-abc");
    expect(url).toBe("wss://api.dukaanly.example.com/api/v1/ws/deliveries/del-123?token=token-abc");
  });

  it("derives ws:// from http:// VITE_API_URL", () => {
    vi.stubEnv("VITE_API_URL", "http://localhost:8000/api/v1");
    const url = getDeliveryWsUrl("del-123", null);
    expect(url).toBe("ws://localhost:8000/api/v1/ws/deliveries/del-123");
  });

  it("appends /api/v1 when VITE_API_URL is the root origin without /api/v1", () => {
    vi.stubEnv("VITE_API_URL", "https://dukaanly-api.onrender.com");
    const url = getDeliveryWsUrl("del-123", "token-xyz");
    expect(url).toBe("wss://dukaanly-api.onrender.com/api/v1/ws/deliveries/del-123?token=token-xyz");
  });

  it("derives wss:// from browser window location when running on https production host", () => {
    // In jsdom or browser environment
    const originalProtocol = window.location.protocol;
    const originalHost = window.location.host;
    try {
      Object.defineProperty(window, "location", {
        value: {
          protocol: "https:",
          host: "dukaanly.example.com",
        },
        writable: true,
      });

      const url = getDeliveryWsUrl("del-123", "token-xyz");
      expect(url).toBe("wss://dukaanly.example.com/api/v1/ws/deliveries/del-123?token=token-xyz");
    } finally {
      Object.defineProperty(window, "location", {
        value: {
          protocol: originalProtocol,
          host: originalHost,
        },
        writable: true,
      });
    }
  });

  it("falls back to ws://localhost:8000 when running on local Vite dev server port 5173", () => {
    const originalHost = window.location.host;
    try {
      Object.defineProperty(window, "location", {
        value: {
          protocol: "http:",
          host: "localhost:5173",
        },
        writable: true,
      });

      const url = getDeliveryWsUrl("del-123", "token-xyz");
      expect(url).toBe("ws://localhost:8000/api/v1/ws/deliveries/del-123?token=token-xyz");
    } finally {
      Object.defineProperty(window, "location", {
        value: {
          protocol: "http:",
          host: originalHost,
        },
        writable: true,
      });
    }
  });
});
