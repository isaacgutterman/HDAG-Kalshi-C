// api.js — thin wrapper around the FastAPI backend
const BASE = "/api";

async function request(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(BASE + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "Request failed");
  }
  return res.json();
}

export const api = {
  getPortfolio:    ()           => request("GET",  "/portfolio"),
  getPositions:    ()           => request("GET",  "/positions"),
  getTrades:       (limit=50)   => request("GET",  `/trades?limit=${limit}`),
  getBalanceHist:  (limit=200)  => request("GET",  `/balance_history?limit=${limit}`),
  getMarkets:      (limit=50)   => request("GET",  `/markets?limit=${limit}`),
  getMarketFeed:   (ticker, n=30) => request("GET", `/markets/${ticker}/feed?limit=${n}`),
  getStrategies:   ()           => request("GET",  "/strategies"),

  placeOrder: (ticker, side, size, limitPrice) =>
    request("POST", "/orders", { ticker, side, size, limit_price: limitPrice }),

  settlePosition: (ticker, side, settlementPrice) =>
    request("POST", "/settle", { ticker, side, settlement_price: settlementPrice }),

  kill:   () => request("POST", "/kill"),
  resume: () => request("POST", "/resume"),

  toggleStrategy: (name) => request("POST", `/strategies/${name}/toggle`),

  runBacktest: (params) => request("POST", "/backtest", params),
};
