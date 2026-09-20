import path from "node:path";
import dotenv from "dotenv";
import { z } from "zod/v4";
import { PATHS } from "./paths.config.ts";

dotenv.config({
	path: path.resolve(PATHS.root, ".env"),
	quiet: true,
});

const envSchema = z.object({
	NODE_ENV: z
		.enum(["development", "production"], {
			error:
				"NODE_ENV is required and must be either 'development' or 'production'.",
		})
		.default("development"),

	LOGFILES: z
		.enum(["context", "single"], {
			error: "LOGFILES must be either 'context' or 'single'.",
		})
		.default("context"),

	PORT: z.coerce
		.number({
			error: "PORT must be a valid number.",
		})
		.default(8000),

	DB_SERVER: z
		.string({
			error: "DB_SERVER is required.",
		})
		.min(1, "DB_SERVER cannot be empty."),

	DB_USER: z
		.string({
			error: "DB_USER is required.",
		})
		.min(1, "DB_USER cannot be empty."),

	DB_PASSWORD: z
		.string({
			error: "DB_PASSWORD is required.",
		})
		.min(1, "DB_PASSWORD cannot be empty."),

	DB_DATABASE: z
		.string({
			error: "DB_DATABASE is required.",
		})
		.min(1, "DB_DATABASE cannot be empty."),

	ACCESS_TOKEN_EXPIRY: z
		.string({
			error: "ACCESS_TOKEN_EXPIRY is required.",
		})
		.min(1, "ACCESS_TOKEN_EXPIRY cannot be empty."),

	REFRESH_TOKEN_EXPIRY: z
		.string({
			error: "REFRESH_TOKEN_EXPIRY is required.",
		})
		.min(1, "REFRESH_TOKEN_EXPIRY cannot be empty."),

	ACCESS_TOKEN_SECRET: z
		.string({
			error: "ACCESS_TOKEN_SECRET is required.",
		})
		.min(1, "ACCESS_TOKEN_SECRET cannot be empty."),

	REFRESH_TOKEN_SECRET: z
		.string({
			error: "REFRESH_TOKEN_SECRET is required.",
		})
		.min(1, "REFRESH_TOKEN_SECRET cannot be empty."),

	TELEGRAM_BOT_TOKEN: z
		.string({
			error: "TELEGRAM_BOT_TOKEN is required.",
		})
		.min(1, "TELEGRAM_BOT_TOKEN cannot be empty."),
});

const parsed = envSchema.safeParse(process.env);

if (!parsed.success) {
	console.error(
		"❌ Invalid environment configuration detected. Review the following field-level diagnostics:",
	);
	console.error(JSON.stringify(z.treeifyError(parsed.error), null, 2));
	process.exit(1);
}

export const env = parsed.data;
