import { env } from "../configs/env.config.ts";

export const LOG_CONTEXTS = [
  "api",
  "auth",
  "db",
  "upload",
  "error",
  "webhook",
  "system",
  "redis",
  "cache",
  "queue",
  "payment",
] as const;

export type LogContext = typeof LOG_CONTEXTS[number];

type LogContextWithWildCard = LogContext | "*";

const logContextMap: Record<typeof env.NODE_ENV, LogContextWithWildCard[]> = {
  production: ["api", "auth", "error", "system", "webhook"],
  development: ["api", "auth", "error", "system", "webhook", "db"],
} as const;

export const ALLOWED_LOG_CONTEXTS: LogContextWithWildCard[] = logContextMap[env.NODE_ENV];
