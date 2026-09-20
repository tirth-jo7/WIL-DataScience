// import { env } from "./env.config.ts";
// import stripAnsi from "strip-ansi";
// import stripAnsi from "strip-ansi";
import type { NextFunction, Request, Response } from "express";
import winston, { type Logger } from "winston";
// import DailyRotateFile from "winston-daily-rotate-file";
// import fs from "fs";
// import path from "path";
import {
  ALLOWED_LOG_CONTEXTS,
  type LogContext,
} from "../constants/logger.constant.ts";

// const LOGFILES = env.LOGFILES || "context";
// const isProduction = env.NODE_ENV === "production";

// const logDir = path.resolve("logs");
// if (!fs.existsSync(logDir)) {
//   fs.mkdirSync(logDir);
// }

const safeMeta = (meta?: Record<string, any>) =>
  JSON.parse(
    JSON.stringify(meta, (_, value) => {
      if (value instanceof Error) {
        return { name: value.name, message: value.message, stack: value.stack };
      }
      return value;
    }),
  );

const baseFormat = winston.format.combine(
  winston.format.timestamp({ format: "DD-MM-YYYY | hh:mm:ss" }),
  winston.format.printf(({ timestamp, level, message, context, meta }) => {
    const tag = context ? `[${context}]` : "";
    const metadata = meta
      ? `\n ↳ meta: ${JSON.stringify(safeMeta(meta), null, 2)}`
      : "";
    return `${timestamp} [${level}] ${tag === "error" ? "message" : tag}: ${message}${metadata}`;
    // const tag = context ? `[${context}]` : "[info]";
    // return `${timestamp} ${tag}: ${message}`;
  }),
);

// const createContextFileTransport = (context: LogContext, filename: string): winston.transport => {
//   const contextFilter = winston.format((info) => {
//     return info.context === context ? info : false;
//   });

//   const logPath = path.join(logDir, "runtime", context);

//   if (!fs.existsSync(logPath)) {
//     fs.mkdirSync(logPath, { recursive: true });
//   }
//   return new DailyRotateFile({
//     filename: path.join(logPath, `${filename}-%DATE%.log`),
//     datePattern: 'YYYY-MM-DD',
//     zippedArchive: true,
//     maxSize: '1024k',
//     maxFiles: '14d',
//     json: false,
//     format: winston.format.combine(
//       // contextWhitelistFilter(),
//       contextFilter(),
//       baseFormat
//     ),
//   });
// };

type LogLevel = "info" | "warn" | "error" | "debug";
type ContextualLogInfo = {
  timestamp: string;
  level: LogLevel;
  message: string;
  context?: LogContext;
  meta?: {
    ip?: string;
    [key: string]: any;
  };
};

const contextWhitelistFilter = winston.format((info: unknown) => {
  const contextualInfo = info as ContextualLogInfo;

  if (!contextualInfo.context) return false;

  if (
    ALLOWED_LOG_CONTEXTS.includes("*") ||
    ALLOWED_LOG_CONTEXTS.includes(contextualInfo.context)
  ) {
    return contextualInfo;
  }

  return false;
});

const baseTransports: winston.transport[] = [];

// if (!isProduction) {
baseTransports.push(
  new winston.transports.Console({
    format: winston.format.combine(
      contextWhitelistFilter(),
      winston.format.colorize(),
      winston.format.timestamp({ format: "DD-MM-YYYY | hh:mm:ss" }),
      winston.format.printf((info) => {
        const { timestamp, level, message, context, meta } =
          info as ContextualLogInfo;
        const ip = meta?.ip ?? "";
        const ipTag = ip ? `IP: ${ip}` : "";
        const tag = context ? `[${context}]` : "";
        const leftMessage = `${timestamp} [${level}] ${tag}: ${message}`;
        // const visibleLength = stripAnsi(leftMessage).length + stripAnsi(ipTag).length;
        // const terminalWidth = process.stdout.columns || 100;
        // const spacing = terminalWidth > visibleLength ? terminalWidth - visibleLength - 7 : 1;
        // return `${leftMessage}${' '.repeat(spacing)}${ipTag}`;
        return leftMessage;
      }),
    ),
  }),
);
// }

// if (isProduction) {
//   if (LOGFILES === "context") {
//     LOG_CONTEXTS.forEach(ctx => {
//       baseTransports.push(createContextFileTransport(ctx, `${ctx}.log`));
//     });
//   } else {
//     baseTransports.push(
//       new winston.transports.File({
//         filename: path.join(logDir, "application.log"),
//         level: "info",
//         format: baseFormat,
//       })
//     );
//   }
// }

const baseLogger = winston.createLogger({
  level: "info",
  transports: baseTransports,
});

class LogManager {
  private static instance: LogManager;
  private logger: Logger;

  private constructor(logger: Logger) {
    this.logger = logger;
  }

  static getInstance(): LogManager {
    if (!LogManager.instance) {
      LogManager.instance = new LogManager(baseLogger);
    }
    return LogManager.instance;
  }

  log(
    level: "info" | "warn" | "error" | "debug",
    message: string,
    context?: LogContext,
    meta?: Record<string, any>,
  ) {
    this.logger.log(level, message, { context, meta });
  }

  info(message: string, context?: LogContext, meta?: Record<string, any>) {
    this.log("info", message, context, meta);
  }

  warn(message: string, context?: LogContext, meta?: Record<string, any>) {
    this.log("warn", message, context, meta);
  }

  error(message: string, context?: LogContext, meta?: Record<string, any>) {
    this.log("error", message, context, meta);
  }

  debug(message: string, context?: LogContext, meta?: Record<string, any>) {
    this.log("debug", message, context, meta);
  }

  raw() {
    return this.logger;
  }
}

const logger = LogManager.getInstance();

export const logApi = (req: Request, res: Response, next: NextFunction) => {
  const { ip, UserCode, timestamp, requestId } = req.meta || {};
  const method = req.method;
  const url = req.originalUrl;

  logger.info(`REQ_RECEIVED: ${method} ${url}`, "api", {
    requestId,
    ip,
    UserCode,
    timestamp,
  });

  res.on("finish", () => {
    const diff = process.hrtime((req as any)._startTime);
    const durationInSeconds = Number((diff[0] + diff[1] / 1e9).toFixed(3));
    const status = res.statusCode;

    logger.info(
      `RES_SENT: ${method} ${url} ${status} - ${durationInSeconds}s`,
      "api",
      {
        requestId,
        ip,
        UserCode,
        status,
        durationInSeconds,
        timestamp,
      },
    );
  });
  next();
};

export const logAuth = (req: Request, _res: Response, next: NextFunction) => {
  logger.info(`${req.method} auth${req.url}`, "auth", {
    ip: req.ip,
  });
  next();
};

export const logWebhook = (req: Request, res: Response, next: NextFunction) => {
  logger.info(`${req.method} webhook${req.url}`, "webhook", {
    ip: req.ip,
  });

  res.on("finish", () => {
    logger.info(`WEBHOOK_RES_SENT`, "webhook");
  });

  next();
};

export default logger;
