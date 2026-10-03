import { randomUUID } from "node:crypto";
import type { MyContext, TelegramBot } from "../configs/telegram.config.ts";
import { RagClient } from "./rag.client.ts";
import type { RagResponse } from "./rag.types.ts";

export class TelegramHandler {
  private readonly ragClient: RagClient;

  constructor(
    private readonly telegram: TelegramBot,
    ragUrl: string,
  ) {
    this.ragClient = new RagClient(ragUrl);
  }

  register(): void {
    const bot = this.telegram.getBot();

    bot.command("start", async (ctx) => {
      await ctx.reply(
        "👋 Welcome!\n\n" +
        "Ask me about student support, wellbeing services, eligibility, processes, or where to get help.",
      );
    });

    bot.command("help", async (ctx) => {
      await ctx.reply(
        "Describe your question in your own words. I can explain verified support options and help you work out the next step.",
      );
    });

    bot.on("message:text", async (ctx) => {
      await this.handleMessage(ctx);
    });
  }

  private async handleMessage(ctx: MyContext): Promise<void> {
    const requestId = randomUUID();

    const request = {
      requestId,
      channel: "telegram" as const,
      user: {
        id: ctx.from.id,
        username: ctx.from.username,
        firstName: ctx.from.first_name,
      },
      message: {
        text: ctx.message.text,
        timestamp: new Date().toISOString(),
      },
    };

    try {
      await ctx.replyWithChatAction("typing");
      const result = await this.ragClient.query(request);
      await this.sendResponse(ctx, result);
    } catch (error) {
      console.error("❌ RAG request failed:", error);
      await ctx.reply(
        "⚠️ I could not reach the student support service right now. Please try again shortly.",
      );
    }
  }

  private async sendResponse(
    ctx: MyContext,
    result: RagResponse,
  ): Promise<void> {
    let message = result.response.text;

    if (result.sources.length > 0) {
      message += "\n\n<b>Sources</b>\n";

      for (const source of result.sources) {
        if (source.url) {
          message += `• <a href="${source.url}">${source.title}</a>\n`;
        } else {
          message += `• ${source.title}\n`;
        }
      }
    }

    await ctx.reply(message, {
      parse_mode: "HTML",
    });
  }
}
