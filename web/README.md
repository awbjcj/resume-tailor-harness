# Web client

This directory contains the React and TypeScript client for Résumé Tailor
Harness. It provides the browser workspace for job discovery, tailoring,
application tracking, and the rest of the product workflow.

## Run it locally

Install the frontend dependencies, then start the development server:

```
npm install
npm run dev
```

Open the address Vite prints, usually <http://localhost:5173>. Requests to
`/api` are proxied to <http://127.0.0.1:8000> by default. Set
`VITE_API_PROXY_TARGET` when your local API uses another address.

## Useful commands

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the Vite development server. |
| `npm run lint` | Run the frontend lint checks. |
| `npm run test:run` | Run the Vitest suite once. |
| `npm run e2e` | Run the Playwright browser tests. |
| `npm run build` | Check translations, type-check, and build the production client. |

## English and Simplified Chinese copy

The client supports English and Simplified Chinese. User-facing copy in
components is collected into the checked-in catalog at
`src/i18n/auto-catalog.json`. Every entry has a hand-written Chinese
translation; the app does not fall back to machine translation.

After changing visible copy, keep its Chinese counterpart clear and equivalent,
then run:

```
npm run i18n:check
npm run i18n:generate
```

The check reports missing or stale entries. The generation step refreshes the
compact runtime catalogs that the app loads for English and Chinese.

## Before you open a pull request

Run the checks that match your change. For most frontend work, that means:

```
npm run lint
npm run test:run
npm run build
```
