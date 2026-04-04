# pump.fun Agent Payments SDK Reference

This page documents the `@pump-fun/agent-payments-sdk` integration pattern used by the `solana-payment-engineer` agent. Use it when building tokenized-agent payment flows on Solana.

---

## Mandatory Pre-Flight Checklist

**NEVER write or modify any code until every item below is confirmed by the user:**

- Agent token mint address (from pump.fun)
- Payment currency decided (USDC or SOL)
- Price/amount confirmed (in smallest unit)
- RPC URL provided or a fallback agreed upon
- Framework confirmed (Next.js, Express, other)

Do not assume defaults. Do not proceed until the user has explicitly answered each one.

---

## Safety Rules

- **NEVER** log, print, or return private keys or secret key material.
- **NEVER** sign transactions on behalf of a user — build the instruction; the user signs.
- Always validate that `amount > 0` before creating an invoice.
- Always ensure `endTime > startTime` and both are valid Unix timestamps.
- Use correct decimal precision: 6 decimals for USDC, 9 for SOL.
- **Always verify payments on the server** using `validateInvoicePayment` before delivering any service. Never trust the client alone.
- **Always verify generated code against this document before delivering it.** Check parameter types, ordering, names, and import paths.

---

## Supported Currencies

| Currency    | Decimals | Smallest unit example    |
| ----------- | -------- | ------------------------ |
| USDC        | 6        | `1000000` = 1 USDC       |
| Wrapped SOL | 9        | `1000000000` = 1 SOL     |

---

## Environment Variables

```env
# Server-side Solana RPC
SOLANA_RPC_URL=https://rpc.solanatracker.io/public

# Client-side Solana RPC (Next.js)
NEXT_PUBLIC_SOLANA_RPC_URL=https://rpc.solanatracker.io/public

# Agent token mint address from pump.fun
AGENT_TOKEN_MINT_ADDRESS=<your-agent-mint-address>

# Payment currency mint
# USDC: EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
# SOL (wrapped): So11111111111111111111111111111111111111112
CURRENCY_MINT=EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
```

**RPC note:** The default Solana public RPC (`https://api.mainnet-beta.solana.com`) does **not** support sending transactions. Ask the user which RPC to use. Free mainnet-beta options:
- **Solana Tracker** — `https://rpc.solanatracker.io/public`
- **Ankr** — `https://rpc.ankr.com/solana`

Read all values from `process.env` at runtime. Never hard-code mint addresses or RPC URLs.

---

## Install

```bash
npm install @pump-fun/agent-payments-sdk@3.0.2 @solana/web3.js@^1.98.0
```

Before installing `@solana/web3.js`, `@solana/spl-token`, or any `@solana/wallet-adapter-*` package, check what versions `@pump-fun/agent-payments-sdk` declares (`npm info @pump-fun/agent-payments-sdk dependencies`) and install matching ranges so npm hoists a single copy.

---

## SDK Setup

```typescript
import { PumpAgent } from "@pump-fun/agent-payments-sdk";
import { PublicKey, Connection } from "@solana/web3.js";

const agentMint = new PublicKey(process.env.AGENT_TOKEN_MINT_ADDRESS!);

// Without connection (HTTP-only verification):
const agent = new PumpAgent(agentMint);

// With connection (enables RPC fallback for verification):
const connection = new Connection(process.env.SOLANA_RPC_URL!);
const agent = new PumpAgent(agentMint, "mainnet", connection);
```

### Constructor

```typescript
new PumpAgent(mint: PublicKey, environment?: "mainnet" | "devnet", connection?: Connection)
```

---

## Building Payment Instructions

Use `buildAcceptPaymentInstructions` to get all instructions needed for a payment.

### Parameters

| Parameter          | Type                         | Description                                                  |
| ------------------ | ---------------------------- | ------------------------------------------------------------ |
| `user`             | `PublicKey`                  | The payer's wallet address                                   |
| `currencyMint`     | `PublicKey`                  | Mint address of the payment currency                         |
| `amount`           | `bigint \| number \| string` | Price in the currency's smallest unit                        |
| `memo`             | `bigint \| number \| string` | Unique invoice identifier (random number)                    |
| `startTime`        | `bigint \| number \| string` | Unix timestamp — when the invoice becomes valid              |
| `endTime`          | `bigint \| number \| string` | Unix timestamp — when the invoice expires                    |
| `tokenProgram`     | `PublicKey` (optional)       | Token program for the currency (defaults to SPL Token)       |
| `computeUnitLimit` | `number` (optional)          | Compute unit budget (default `100_000`)                      |
| `computeUnitPrice` | `number` (optional)          | Priority fee in microlamports per CU                         |

```typescript
const ixs = await agent.buildAcceptPaymentInstructions({
  user: userPublicKey,
  currencyMint,
  amount: "1000000",   // 1 USDC
  memo: "123456789",   // unique invoice identifier
  startTime: "1700000000",
  endTime: "1700086400",
});
```

The `amount`, `memo`, `startTime`, and `endTime` must exactly match when verifying later. Generate a unique `memo` per invoice: `Math.floor(Math.random() * 900000000000) + 100000`.

---

## Deriving the Invoice ID

```typescript
import { getInvoiceIdPDA } from "@pump-fun/agent-payments-sdk";

const [invoiceId] = getInvoiceIdPDA(
  tokenMint,    // PublicKey
  currencyMint, // PublicKey
  amount,       // number
  memo,         // number
  startTime,    // number
  endTime,      // number
);
```

All numeric parameters are plain `number`. Returns `[PublicKey, number]`; use the first element.

Pre-check for duplicates before building a transaction:

```typescript
const accountInfo = await connection.getAccountInfo(invoiceId);
if (accountInfo !== null) {
  // Already paid — generate a new memo
}
```

---

## Full Transaction Flow

### Step 1: Generate Invoice Parameters (Server)

```typescript
function generateInvoiceParams() {
  // Memo must be a unique positive integer. The range [100000, ~900 billion]
  // avoids small values that could collide with reserved or trivially-guessable IDs.
  const memo = Math.floor(Math.random() * 900000000000) + 100000;
  const now = Math.floor(Date.now() / 1000);
  return { amount: 1000000, memo, startTime: now, endTime: now + 86400 };
}
```

### Step 2: Build and Serialize Transaction (Server)

```typescript
import { Connection, PublicKey, Transaction } from "@solana/web3.js";
import { PumpAgent } from "@pump-fun/agent-payments-sdk";

async function buildPaymentTransaction(params: {
  userWallet: string; amount: string; memo: string;
  startTime: string; endTime: string;
}) {
  const connection = new Connection(process.env.SOLANA_RPC_URL!);
  const agent = new PumpAgent(
    new PublicKey(process.env.AGENT_TOKEN_MINT_ADDRESS!), "mainnet", connection
  );
  const instructions = await agent.buildAcceptPaymentInstructions({
    user: new PublicKey(params.userWallet),
    currencyMint: new PublicKey(process.env.CURRENCY_MINT!),
    amount: params.amount, memo: params.memo,
    startTime: params.startTime, endTime: params.endTime,
  });
  const { blockhash } = await connection.getLatestBlockhash("confirmed");
  const tx = new Transaction();
  tx.recentBlockhash = blockhash;
  tx.feePayer = new PublicKey(params.userWallet);
  tx.add(...instructions);
  return { transaction: tx.serialize({ requireAllSignatures: false }).toString("base64") };
}
```

### Step 3: Deserialize, Sign, and Send (Client)

```typescript
async function signAndSendPayment(
  txBase64: string,
  signTransaction: (tx: Transaction) => Promise<Transaction>,
  connection: Connection,
): Promise<string> {
  const tx = Transaction.from(Buffer.from(txBase64, "base64"));
  const signedTx = await signTransaction(tx);
  const signature = await connection.sendRawTransaction(signedTx.serialize(), {
    skipPreflight: false, preflightCommitment: "confirmed",
  });
  const latestBlockhash = await connection.getLatestBlockhash("confirmed");
  await connection.confirmTransaction({ signature, ...latestBlockhash }, "confirmed");
  return signature;
}
```

Call `useWallet()` and `useConnection()` at the top level of the component; pass `signTransaction` and `connection` into the async helper.

---

## Verify Payment (Server)

```typescript
async function verifyPayment(params: {
  user: string; currencyMint: string; amount: number;
  memo: number; startTime: number; endTime: number;
}): Promise<boolean> {
  const agent = new PumpAgent(new PublicKey(process.env.AGENT_TOKEN_MINT_ADDRESS!));
  const invoiceParams = {
    user: new PublicKey(params.user),
    currencyMint: new PublicKey(params.currencyMint),
    amount: params.amount,   // number, not string
    memo: params.memo,       // number, not string
    startTime: params.startTime,
    endTime: params.endTime,
  };
  for (let attempt = 0; attempt < 10; attempt++) {
    if (await agent.validateInvoicePayment(invoiceParams)) return true;
    await new Promise((r) => setTimeout(r, 2000));
  }
  return false;
}
```

`validateInvoicePayment` expects `amount`, `memo`, `startTime`, `endTime` as `number`. Parse strings first: `Number(memo)`.

---

## End-to-End Flow Summary

```
1. Agent generates: unique memo (number), startTime, endTime, amount
2. Server: buildAcceptPaymentInstructions({...}) → TransactionInstruction[]
3. Server: builds Transaction (blockhash + feePayer + instructions) → base64 string
4. Client: Transaction.from(Buffer.from(txBase64, "base64"))
5. Client: signTransaction(tx) — wallet prompts user
6. Client: sendRawTransaction + confirmTransaction
7. Server: validateInvoicePayment({...same params...}) → true/false
8. Server delivers service on true; asks user to retry on false
```

---

## References

- Wallet integration: <https://raw.githubusercontent.com/pump-fun/pump-fun-skills/refs/heads/main/tokenized-agents/references/WALLET_INTEGRATION.md>
- Test scenarios & troubleshooting: <https://raw.githubusercontent.com/pump-fun/pump-fun-skills/refs/heads/main/tokenized-agents/references/SCENARIOS.md>
