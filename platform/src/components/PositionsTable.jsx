export default function PositionsTable({ positions }) {
  return (
    <div className="card" style={{ flex: 1 }}>
      <div className="card-title">Open Positions ({positions.length})</div>
      {positions.length === 0 ? (
        <div className="empty">No open positions</div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Side</th>
                <th>Size</th>
                <th>Avg Fill</th>
                <th>Current</th>
                <th>Unrealized P&L</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p, i) => {
                const upnl = p.unrealized_pnl;
                const pnlClass = upnl > 0 ? "positive" : upnl < 0 ? "negative" : "neutral";
                return (
                  <tr key={i}>
                    <td style={{ fontFamily: "monospace", fontSize: 12 }}>{p.ticker}</td>
                    <td>
                      <span className={`badge badge-${p.side.toLowerCase()}`}>{p.side}</span>
                    </td>
                    <td>{p.size}</td>
                    <td>{p.avg_fill_price}¢</td>
                    <td>{p.current_price}¢</td>
                    <td className={pnlClass}>
                      {upnl >= 0 ? "+" : ""}${upnl.toFixed(4)}
                    </td>
                    <td style={{ color: "var(--muted)", fontSize: 11 }}>
                      {new Date(p.opened_at).toLocaleTimeString()}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
