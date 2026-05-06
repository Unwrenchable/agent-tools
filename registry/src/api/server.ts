// ─── Express application factory ─────────────────────────────────────────────

import express, { type Express } from "express";
import { buildRouter } from "./routes.js";

/**
 * Create and configure the Express application.
 * Exported for use in tests without starting the HTTP listener.
 */
export function createApp(): Express {
  const app = express();

  // Parse JSON bodies for all routes except the webhook, which needs raw
  // bytes for HMAC verification (the webhook route uses its own parser).
  app.use(express.json());

  // Attach all API routes.
  app.use(buildRouter());

  return app;
}

/**
 * Start the HTTP server on the given port.
 * Returns a promise that resolves once the server is listening.
 */
export function startServer(port: number): Promise<void> {
  return new Promise((resolve) => {
    const app = createApp();
    app.listen(port, () => {
      console.log(`[server] listening on http://0.0.0.0:${port}`);
      resolve();
    });
  });
}
