// ─── RealAI HTTP client ───────────────────────────────────────────────────────
//
// Thin wrapper around the RealAI v1/chat/completions endpoint.
// Configuration is driven entirely by environment variables so the same
// module works in both local dev and production (Vercel / Render).
//
// Required env vars:
//   REALAI_API_URL — base URL, e.g. https://api.realai.example.com
//   REALAI_API_KEY — bearer token
//
// Optional env vars:
//   REALAI_MODEL   — model identifier (default: realai-psi)

/** An OpenAI-compatible chat message. */
export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

/** Minimal subset of the OpenAI chat completion response we care about. */
export interface ChatCompletion {
  id: string;
  object: string;
  model: string;
  choices: Array<{
    index: number;
    message: ChatMessage;
    finish_reason: string;
  }>;
  usage?: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
}

export interface RealAIClientOptions {
  /** Override the model for a single call. */
  model?: string;
}

// ── Configuration ─────────────────────────────────────────────────────────────

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Missing required environment variable: ${name}. ` +
        `Set it in .env.local or your deployment environment.`,
    );
  }
  return value;
}

const DEFAULT_MODEL = "realai-psi";

// ── Client ────────────────────────────────────────────────────────────────────

/**
 * Send a chat-completion request to the RealAI API.
 *
 * @param messages - OpenAI-style message array (system + user turns).
 * @param options  - Optional per-call overrides (e.g. model).
 * @returns        The parsed ChatCompletion response.
 */
export async function chatCompletion(
  messages: ChatMessage[],
  options: RealAIClientOptions = {},
): Promise<ChatCompletion> {
  const apiUrl = requireEnv("REALAI_API_URL");
  const apiKey = requireEnv("REALAI_API_KEY");
  const model = options.model ?? process.env["REALAI_MODEL"] ?? DEFAULT_MODEL;

  const endpoint = `${apiUrl.replace(/\/$/, "")}/v1/chat/completions`;

  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({ model, messages }),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "(unreadable body)");
    throw new Error(
      `RealAI API error ${response.status} ${response.statusText}: ${body}`,
    );
  }

  return response.json() as Promise<ChatCompletion>;
}

/**
 * Extract the text content from the first choice of a chat completion.
 * Throws if the response contains no choices.
 */
export function extractContent(completion: ChatCompletion): string {
  const choice = completion.choices[0];
  if (!choice) throw new Error("RealAI returned no choices in the response.");
  return choice.message.content;
}
