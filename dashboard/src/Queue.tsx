import { listClaims } from "./api";
import { label, money, STATUSES, VERDICT_LABELS } from "./format";
import { usePolling } from "./hooks";
import { StatusChip } from "./StatusChip";

export function Queue() {
  const { data: claims, error } = usePolling(listClaims, 3000);

  return (
    <>
      <h1>Claims queue</h1>
      {error && <p className="alert">The backend is not responding.</p>}
      {claims && (
        <>
          <section className="tiles" aria-label="Claims by status">
            {STATUSES.map((status) => (
              <div className="tile" key={status}>
                <strong>
                  {claims.filter((claim) => claim.status === status).length}
                </strong>
                <StatusChip status={status} />
              </div>
            ))}
          </section>
          <section className="panel table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Claim</th>
                  <th>Type</th>
                  <th>Customer</th>
                  <th>Summary</th>
                  <th className="amount">Claimed</th>
                  <th>Status</th>
                  <th>Decision</th>
                  <th className="amount">Payout</th>
                </tr>
              </thead>
              <tbody>
                {claims.map((claim) => (
                  <tr key={claim.claim_id}>
                    <td className="mono">
                      <a href={`#/claims/${claim.claim_id}`}>
                        {claim.claim_id}
                      </a>
                    </td>
                    <td>{label(claim.claim_type)}</td>
                    <td>{claim.customer_name}</td>
                    <td>{claim.summary}</td>
                    <td className="amount mono">
                      {money(claim.amount_claimed)}
                    </td>
                    <td>
                      <StatusChip status={claim.status} />
                    </td>
                    <td>{claim.decision && VERDICT_LABELS[claim.decision]}</td>
                    <td className="amount mono">
                      {claim.payout !== null && money(claim.payout)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </>
  );
}
