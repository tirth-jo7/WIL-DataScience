// telegram.config.ts - Updated to NOT auto-start

import fs from 'node:fs';
import https from 'node:https';
import path from 'node:path';
import {
  type Conversation,
  type ConversationFlavor,
  conversations,
  createConversation,
} from '@grammyjs/conversations';
import { I18n, type I18nFlavor } from '@grammyjs/i18n';
import { Bot, type Context, type SessionFlavor, session } from 'grammy';
import fetch from 'node-fetch';
import { ErrorCode } from '../constants/errors.constant.ts';
import { AppError } from '../utils/app-error.ts';
import { env } from './env.config.ts';
import logger from './logger.config.ts';

// ==================== TYPES ====================

export type BotMode = 'production' | 'development' | 'testing';

export interface TelegramConfig {
  token: string;
  mode: BotMode;
  parseMode: 'HTML' | 'Markdown' | 'MarkdownV2';
  allowedUpdates?: Array<
    keyof Pick<
      import('grammy/types').Update,
      | 'message'
      | 'callback_query'
      | 'inline_query'
      | 'my_chat_member'
      | 'chat_member'
      | 'chat_join_request'
      | 'message_reaction'
    >
  >;
  dropPendingUpdates: boolean;
  webhook?: {
    enabled: boolean;
    domain: string;
    path: string;
    secretToken?: string;
    maxConnections?: number;
  };
  polling?: {
    timeout: number;
    limit: number;
    allowedUpdates?: string[];
  };
}

// ==================== SESSION TYPES ====================

interface SessionData {
  userId?: number;
  chatId?: number;
  step?: string;
  data?: Record<string, any>;
  lastActivity?: number;
  preferences?: {
    language?: string;
    notifications?: boolean;
  };
}

// Update MyContext to include ConversationFlavor
export type MyContext = Context &
  SessionFlavor<SessionData> &
  I18nFlavor &
  ConversationFlavor<Context>;

export type MyConversation = Conversation<MyContext>;

// ==================== CONFIG ====================

const config: TelegramConfig = {
  token: env.TELEGRAM_BOT_TOKEN || '',
  mode: (env.NODE_ENV as BotMode) || 'development',
  parseMode: 'HTML',
  dropPendingUpdates: true,
  // webhook: {
  //   enabled: false,
  //   domain: env.TELEGRAM_WEBHOOK_DOMAIN || '',
  //   path: '/webhook',
  //   secretToken: env.TELEGRAM_WEBHOOK_SECRET,
  //   maxConnections: 100,
  // },
  polling: {
    timeout: 30,
    limit: 100,
  },
};

// ==================== HTTP AGENT ====================

const agent = new https.Agent({
  family: 4,
  keepAlive: true,
  keepAliveMsecs: 1000,
  maxSockets: 50,
  maxFreeSockets: 10,
  timeout: 60000,
});

// ==================== I18N ====================

// Check if locales directory exists
const localesDir = path.join(process.cwd(), 'locales');
const hasLocalesDir =
  fs.existsSync(localesDir) && fs.statSync(localesDir).isDirectory();

// Default translations as fallback
const defaultTranslations = {
  en: {
    hello: 'Hello',
    goodbye: 'Goodbye',
    welcome: 'Welcome to the bot!',
    error: 'An error occurred. Please try again.',
  },
};

// Build i18n config
const i18nConfig: any = {
  defaultLocale: 'en',
  useSession: true,
  fluentBundleOptions: {
    useIsolating: false,
  },
};

if (hasLocalesDir) {
  i18nConfig.directory = localesDir;
  logger.info('📚 Loading translations from locales directory', 'system');
} else {
  i18nConfig.translations = defaultTranslations;
  logger.warn(
    '⚠️ Locales directory not found, using default translations',
    'system',
  );

  // Create locales directory in development to help
  if (env.NODE_ENV === 'development') {
    try {
      fs.mkdirSync(localesDir, { recursive: true });
      fs.writeFileSync(
        path.join(localesDir, 'en.json'),
        JSON.stringify(defaultTranslations.en, null, 2),
      );
      logger.info(
        '📁 Created locales directory with default translations',
        'system',
      );
    } catch (_error) {
      // Ignore directory creation errors
    }
  }
}

const i18n = new I18n<MyContext>(i18nConfig);

// ==================== BOT FACTORY ====================

export class TelegramBot {
  private bot!: Bot<MyContext>;
  private readonly config: TelegramConfig;
  private isRunning = false;
  private startTime?: Date;

  constructor(config: TelegramConfig) {
    this.config = config;
    this.initializeBot();
  }

  private initializeBot(): void {
    if (!this.config.token) {
      throw AppError.database('TELEGRAM_BOT_TOKEN is not set', {
        code: ErrorCode.DB_ERROR,
        originalError: new Error('Missing token'),
      });
    }

    // Create bot instance
    this.bot = new Bot<MyContext>(this.config.token, {
      client: {
        fetch: (url, init) =>
          fetch(url as string, {
            ...init,
            agent,
            // Add retry logic
            // @ts-expect-error - node-fetch specific
            retry: 3,
            retryDelay: 1000,
          }),
        apiRoot: 'https://api.telegram.org',
        timeoutSeconds: 30,
        canUseWebhookReply: (method) => method === 'sendMessage',
      },
    });

    // Setup middleware
    this.setupMiddleware();
  }

  private setupMiddleware(): void {
    // 1. Session
    this.bot.use(
      session({
        initial: (): SessionData => ({
          userId: undefined,
          chatId: undefined,
          step: undefined,
          data: {},
          lastActivity: Date.now(),
          preferences: {
            language: 'en',
            notifications: true,
          },
        }),
        storage: this.getSessionStorage(),
      }),
    );

    // 2. I18n
    this.bot.use(i18n);

    // 3. Global error handling
    this.bot.catch((error) => {
      logger.error(`❌ Telegram bot error: ${error}`, 'error');

      // Don't crash on errors
      if (error instanceof Error) {
        logger.error(`Error details: ${error.message}`, 'error');
        logger.error(`Stack: ${error.stack}`, 'error');
      }
    });

    // 4. Logging middleware
    this.bot.use(async (ctx, next) => {
      const start = Date.now();

      ctx.session.lastActivity = start;

      if (ctx.from) {
        ctx.session.userId = ctx.from.id;
        ctx.session.chatId = ctx.chat?.id;
      }

      logger.info(
        `📨 [${ctx.update.update_id}] ${ctx.from?.username || 'unknown'} -> ${(ctx as any).updateType || 'unknown'}`,
        'api',
      );

      try {
        await next();
        const ms = Date.now() - start;
        logger.debug(`⏱️ [${ctx.update.update_id}] processed in ${ms}ms`, 'api');
      } catch (error) {
        logger.error(`❌ Error in middleware: ${error}`, 'error');
        throw error;
      }
    });
  }

  private getSessionStorage() {
    // You can implement different storage backends here
    // For now, using in-memory storage

    // In production, you'd want to use:
    // - Redis: https://github.com/grammyjs/storage-redis
    // - File: https://github.com/grammyjs/storage-file
    // - Database: Custom implementation

    // if (env.REDIS_URL) {
    //   return new RedisAdapter(env.REDIS_URL);
    // }

    return undefined; // Default in-memory storage
  }

  // ==================== CONVERSATIONS ====================

  public registerConversation(
    conversation: (conversation: MyConversation) => any,
    name: string,
  ): void {
    // Apply conversations middleware first
    this.bot.use(conversations());
    // Then register the specific conversation
    this.bot.use(createConversation(conversation, name));
  }

  // ==================== START/STOP ====================

  public async start(retryCount: number = 0): Promise<void> {
    if (this.isRunning) {
      logger.warn('⚠️ Bot is already running', 'system');
      return;
    }

    try {
      // Get bot info
      const me = await this.bot.api.getMe();
      logger.info(`🤖 Bot started: @${me.username} (ID: ${me.id})`, 'system');
      logger.info(`📊 Mode: ${this.config.mode}`, 'system');

      // Setup webhook or polling
      if (this.config.webhook?.enabled) {
        await this.startWebhook();
      } else {
        await this.startPolling();
      }

      this.isRunning = true;
      this.startTime = new Date();

      // Log supported commands
      await this.logCommands();
    } catch (error: any) {
      // Handle 409 conflict specifically
      if (error?.error_code === 409 && retryCount < 3) {
        logger.warn(`⚠️ Bot conflict detected (another instance running), attempting to force stop...`, 'system');

        try {
          // Try to force stop the other instance
          await this.forceStop();
          // Wait a bit longer
          await new Promise(resolve => setTimeout(resolve, 3000));
          logger.info(`🔄 Retrying bot start (attempt ${retryCount + 2}/3)...`, 'system');
          return this.start(retryCount + 1);
        } catch (_forceError) {
          // If force stop fails, just retry anyway
          logger.warn(`⚠️ Force stop failed, retrying anyway (${retryCount + 1}/3)...`, 'system');
          await new Promise(resolve => setTimeout(resolve, 3000));
          return this.start(retryCount + 1);
        }
      }

      logger.error(`❌ Failed to start bot: ${error}`, 'error');
      throw AppError.database('Failed to start bot', {
        code: ErrorCode.DB_ERROR,
        originalError: error,
      });
    }
  }

  // Add this method to the TelegramBot class
  public async forceStop(): Promise<void> {
    try {
      // Get the current updates to get the latest offset
      const updates = await this.bot.api.getUpdates({
        offset: -1,
        limit: 1,
        timeout: 5,
      });

      // Get the latest update ID
      const latestUpdateId = updates.length > 0 ? updates[updates.length - 1]!.update_id : 0;

      // Send a getUpdates request with offset to effectively "stop" the polling
      await this.bot.api.getUpdates({
        offset: latestUpdateId + 1,
        limit: 1,
        timeout: 5,
      });

      logger.info('🛑 Force stopped bot polling', 'system');
    } catch (error) {
      logger.error(`❌ Failed to force stop bot: ${error}`, 'error');
    }
  }

  private async startPolling(): Promise<void> {
    const pollingConfig = this.config.polling || {};

    try {
      // First, try to delete any existing webhook to clean up
      await this.bot.api.deleteWebhook();
      logger.info('🔗 Cleaned up existing webhook', 'system');
    } catch (_error) {
      // Ignore if no webhook exists
    }

    // Add a small delay to let the API settle
    await new Promise(resolve => setTimeout(resolve, 1000));

    await this.bot.start({
      drop_pending_updates: true, // Always drop pending updates on start
      allowed_updates: this.config.allowedUpdates as any,
      onStart: (botInfo) => {
        logger.info(`✅ Bot @${botInfo.username} started polling`, 'system');
      },
      ...pollingConfig,
    });
  }

  private async startWebhook(): Promise<void> {
    const webhook = this.config.webhook!;

    // Set webhook
    await this.bot.api.setWebhook(`${webhook.domain}${webhook.path}`, {
      secret_token: webhook.secretToken,
      max_connections: webhook.maxConnections,
      drop_pending_updates: this.config.dropPendingUpdates,
      allowed_updates: this.config.allowedUpdates,
    });

    // Start webhook server
    // This would typically be handled by your main server
    logger.info(
      `🔗 Webhook set to: ${webhook.domain}${webhook.path}`,
      'system',
    );
  }

  public async stop(): Promise<void> {
    if (!this.isRunning) {
      logger.warn('⚠️ Bot is not running', 'system');
      return;
    }

    try {
      // Remove webhook if set
      if (this.config.webhook?.enabled) {
        await this.bot.api.deleteWebhook();
        logger.info('🔗 Webhook removed', 'system');
      }

      // Stop bot
      await this.bot.stop();
      this.isRunning = false;

      const uptime = this.getUptime();
      logger.info(`🛑 Bot stopped (uptime: ${uptime})`, 'system');
    } catch (error) {
      logger.error(`❌ Error stopping bot: ${error}`, 'error');
    }
  }

  public async restart(): Promise<void> {
    await this.stop();
    await this.start();
  }

  // ==================== UTILITIES ====================

  public getBot(): Bot<MyContext> {
    return this.bot;
  }

  public getStatus(): {
    isRunning: boolean;
    startTime?: Date;
    uptime?: string;
    mode: BotMode;
    webhookEnabled: boolean;
  } {
    return {
      isRunning: this.isRunning,
      startTime: this.startTime,
      uptime: this.getUptime(),
      mode: this.config.mode,
      webhookEnabled: this.config.webhook?.enabled || false,
    };
  }

  private getUptime(): string | undefined {
    if (!this.startTime) return undefined;
    const diff = Date.now() - this.startTime.getTime();
    const seconds = Math.floor(diff / 1000);
    const minutes = Math.floor(seconds / 60);
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);

    if (days > 0) return `${days}d ${hours % 24}h`;
    if (hours > 0) return `${hours}h ${minutes % 60}m`;
    if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
    return `${seconds}s`;
  }

  private async logCommands(): Promise<void> {
    try {
      const commands = await this.bot.api.getMyCommands();
      if (commands.length > 0) {
        logger.info(`📋 Registered commands:`, 'system');
        commands.forEach((cmd) => {
          logger.info(`  /${cmd.command} - ${cmd.description}`, 'system');
        });
      }
    } catch (_error) {
      logger.debug('Could not fetch commands', 'system');
    }
  }

  // ==================== HEALTH CHECK ====================

  public async healthCheck(): Promise<{
    status: 'ok' | 'error';
    message: string;
    timestamp: Date;
  }> {
    try {
      const me = await this.bot.api.getMe();
      return {
        status: 'ok',
        message: `Bot @${me.username} is healthy`,
        timestamp: new Date(),
      };
    } catch (error) {
      return {
        status: 'error',
        message: `Health check failed: ${error}`,
        timestamp: new Date(),
      };
    }
  }
}

// ==================== BOT MANAGER ====================

export class BotManager {
  private bots = new Map<string, TelegramBot>();
  private defaultBotName: string;

  constructor(defaultBotName: string = 'default') {
    this.defaultBotName = defaultBotName;
  }

  registerBot(name: string, config: TelegramConfig): void {
    if (this.bots.has(name)) {
      throw AppError.database(`Bot "${name}" is already registered`, {
        code: ErrorCode.DB_ERROR,
        originalError: new Error('Bot already exists'),
      });
    }

    const bot = new TelegramBot(config);
    this.bots.set(name, bot);
    logger.info(`🤖 Bot "${name}" registered`, 'system');
  }

  async getBot(name?: string): Promise<TelegramBot> {
    const botName = name || this.defaultBotName;
    const bot = this.bots.get(botName);

    if (!bot) {
      throw AppError.database(`Bot "${botName}" not found`, {
        code: ErrorCode.DB_ERROR,
        originalError: new Error('Bot not found'),
      });
    }

    return bot;
  }

  async startAll(): Promise<void> {
    const promises = Array.from(this.bots.values()).map((bot) => bot.start());
    await Promise.all(promises);
    logger.info(`✅ ${this.bots.size} bots started`, 'system');
  }

  async stopAll(): Promise<void> {
    const promises = Array.from(this.bots.values()).map((bot) => bot.stop());
    await Promise.all(promises);
    logger.info(`🛑 All bots stopped`, 'system');
  }

  async getSummary(): Promise<
    { name: string; status: 'running' | 'stopped'; uptime?: string }[]
  > {
    return Array.from(this.bots.entries()).map(([name, bot]) => {
      const status = bot.getStatus();
      return {
        name,
        status: status.isRunning ? 'running' : 'stopped',
        uptime: status.uptime,
      };
    });
  }
}

// ==================== SINGLETON INSTANCE ====================

export const botManager = new BotManager();

// ==================== IMPORTANT: DO NOT AUTO-START ====================
// Create default bot instance but DON'T auto-start it
// The bot should be started explicitly by the application
const defaultBot = new TelegramBot(config);

// Export the default bot for use in the application
export default defaultBot;

// ==================== GRACEFUL SHUTDOWN ====================
// Remove the auto-shutdown handlers from here
// They should be handled by the main application

// ==================== ENHANCED CONFIG EXPORT ====================

export const telegramConfig = {
  config,
  defaultBot,
  botManager,
  i18n,

  // Convenience function similar to database()
  getBot: async (name?: string) => {
    return await botManager.getBot(name);
  },

  // Register multiple bots
  registerBots: (bots: Record<string, Partial<TelegramConfig>>) => {
    Object.entries(bots).forEach(([name, botConfig]) => {
      const mergedConfig: TelegramConfig = {
        ...config,
        ...botConfig,
        token: botConfig.token || env.TELEGRAM_BOT_TOKEN || '',
      };

      if (!mergedConfig.token) {
        throw AppError.database(`TELEGRAM_BOT_TOKEN for "${name}" is not set`, {
          code: ErrorCode.DB_ERROR,
          originalError: new Error('Missing token'),
        });
      }

      botManager.registerBot(name, mergedConfig);
    });
  },

  // Health check
  healthCheck: async (botName?: string) => {
    const bot = await botManager.getBot(botName);
    return bot.healthCheck();
  },
};

export { config as defaultTelegramConfig };
