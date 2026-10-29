import { type SyntheticEvent, useState } from "react";
import { type Claim, type Handler, listHandlers, signOff } from "./api";
import { message, money, VERDICT_LABELS } from "./format";
import { usePolling } from "./hooks";

export function DecisionPanel({
  claim,
  onChange,
}: Readonly<{ claim: Claim; onChange: () => void }>) {
  const { data: handlers = [] } = usePolling(listHandlers, 0);
  const { decision, payment, sign_off: signedOff } = claim;

  if (!decision) {
    return (
      <section className="panel">
        <h2>Decision</h2>
        <p className="muted">
          {claim.status === "in_progress"
            ? "The agent is working on this claim."
            : "No decision yet."}
        </p>
      </section>
    );
  }

  const signer = handlers.find((h) => h.handler_id === signedOff?.handler_id);
  return (
    <section className="panel">
      <h2>Decision</h2>
      <p className="verdict">
        {VERDICT_LABELS[decision.decision]}
        {decision.decision === "approve" && (
          <span className="mono"> {money(decision.payout)}</span>
        )}
      </p>
      <p>{decision.reason}</p>
      <p className="muted">{decision.policy_section}</p>
      {payment && (
        <p>
          Paid <span className="mono">{money(payment.amount)}</span>
          {signer && ` after sign-off by ${signer.name}`}.
        </p>
      )}
      {claim.status === "awaiting_sign_off" && (
        <SignOffForm
          claimId={claim.claim_id}
          payout={decision.payout}
          handlers={handlers}
          onDone={onChange}
        />
      )}
    </section>
  );
}

function SignOffForm({
  claimId,
  payout,
  handlers,
  onDone,
}: Readonly<{
  claimId: string;
  payout: number;
  handlers: Handler[];
  onDone: () => void;
}>) {
  const [handlerId, setHandlerId] = useState("");
  const [problem, setProblem] = useState<string>();

  const submit = (event: SyntheticEvent) => {
    event.preventDefault();
    signOff(claimId, handlerId).then(onDone, (reason: unknown) => {
      setProblem(message(reason));
    });
  };

  return (
    <form className="sign-off" onSubmit={submit}>
      <p className="alert">Payment waiting for a handler&apos;s sign-off.</p>
      <label>
        Handler{" "}
        <select
          value={handlerId}
          onChange={(event) => {
            setHandlerId(event.target.value);
          }}
        >
          <option value="">Choose a handler</option>
          {handlers
            .filter((handler) => handler.can_approve_over_limit)
            .map((handler) => (
              <option key={handler.handler_id} value={handler.handler_id}>
                {handler.name}
              </option>
            ))}
        </select>
      </label>
      <button className="button" type="submit" disabled={!handlerId}>
        Sign off and pay {money(payout)}
      </button>
      {problem && <p className="alert">{problem}</p>}
    </form>
  );
}
