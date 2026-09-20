import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..", "..");

export const PATHS = {
  root: ROOT,
  public: path.join(ROOT, "public"),
  uploads: path.join(ROOT, "uploads"),
  logs: path.join(ROOT, "logs"),
} as const;