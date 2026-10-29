import { useCallback, useState } from "react";
import { type Claim, getClaim, getPolicy, listSteps, runAgent } from "./api";
import { DecisionPanel } from "./DecisionPanel";
import { label, message, money } from "./format";
import { usePolling } from "./hooks";
import { StatusChip } from "./StatusChip";
import { Steps } from "./Steps";

export function ClaimPage({ claimId }: Readonly<{ claimId: string }>) {
  const load = useCallback(
    () => Promise.all([getClaim(claimId), listSteps(claimId)]),
    [claimId],
  );
  const { data, error, refresh } = usePolling(load, 1000);
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<string>();

  if (!data) {
    return error ? <p className="alert">{error}</p> : <p>Loading the claim</p>;
  }
  const [claim, steps] = data;

  const start = () => {
    setStarting(true);
    setProblem(undefined);
    runAgent(claimId)
      .then(refresh, (reason: unknown) => {
        setProblem(message(reason));
      })
      .finally(() => {
        setStarting(false);
      });
  };

  return (
    <>
      <p>
        <a href="#/">Back to the queue</a>
      </p>
      <h1>
        <span className="mono">{claim.claim_id}</span> {claim.summary}
      </h1>
      <div className="title-row">
        <StatusChip status={claim.status} />
        {claim.status === "waiting" && (
          <button
            className="button"
            type="button"
            onClick={start}
            disabled={starting}
          >
            Run the agent
          </button>
        )}
      </div>
      {problem && <p className="alert">{problem}</p>}
      <div className="claim-grid">
        <div>
          <ClaimDetails claim={claim} />
          <PolicySummary policyId={claim.policy_id} />
        </div>
        <div>
          <DecisionPanel claim={claim} onChange={refresh} />
          <Steps steps={steps} working={claim.status === "in_progress"} />
        </div>
      </div>
    </>
  );
}

function ClaimDetails({ claim }: Readonly<{ claim: Claim }>) {
  return (
    <section className="panel">
      <h2>The claim</h2>
      <dl className="facts">
        <dt>Type</dt>
        <dd>{label(claim.claim_type)}</dd>
        <dt>Incident</dt>
        <dd>
          {claim.incident_date}, {claim.incident_location}
        </dd>
        <dt>Submitted</dt>
        <dd>{claim.submitted_on}</dd>
        <dt>Claimed</dt>
        <dd className="mono">{money(claim.amount_claimed)}</dd>
      </dl>
      <h3>The customer&apos;s story</h3>
      <p>{claim.story}</p>
      <h3>Items</h3>
      <div className="table-wrap">
        <table>
          <tbody>
            {claim.items.map((item) => (
              <tr key={item.description}>
                <td>{item.description}</td>
                <td>{label(item.category)}</td>
                <td className="amount mono">{money(item.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h3>Documents</h3>
      {claim.documents.map((document) => (
        <div className="document" key={document.name}>
          <strong>{document.name}</strong>{" "}
          <span className="muted">{label(document.type)}</span>
          <p>{document.content}</p>
        </div>
      ))}
    </section>
  );
}

function PolicySummary({ policyId }: Readonly<{ policyId: string }>) {
  const load = useCallback(() => getPolicy(policyId), [policyId]);
  const { data: policy } = usePolling(load, 0);
  if (!policy) return null;

  return (
    <section className="panel">
      <h2>The policy</h2>
      <dl className="facts">
        <dt>Policy</dt>
        <dd className="mono">{policy.policy_id}</dd>
        <dt>Plan</dt>
        <dd>{policy.plan_details.name}</dd>
        <dt>Add-ons</dt>
        <dd>
          {policy.add_on_details.map((addOn) => addOn.name).join(", ") ||
            "None"}
        </dd>
        <dt>Bought</dt>
        <dd>{policy.purchased_on}</dd>
        <dt>Trip</dt>
        <dd>
          {policy.trip.destination}, {policy.trip.departs_on} to{" "}
          {policy.trip.returns_on}
        </dd>
        <dt>Trip cost</dt>
        <dd className="mono">{money(policy.trip.trip_cost)}</dd>
        <dt>Travelers</dt>
        <dd>{policy.travelers.join(", ")}</dd>
      </dl>
    </section>
  );
}
