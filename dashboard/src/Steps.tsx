import type { Step } from "./api";
import { time } from "./format";

const KIND_LABELS: Record<Step["kind"], string> = {
  model: "Agent",
  tool_call: "Tool call",
  tool_result: "Tool result",
  error: "Error",
};

export function Steps({
  steps,
  working,
}: Readonly<{ steps: Step[]; working: boolean }>) {
  return (
    <section className="panel">
      <h2>What the agent did</h2>
      {working && (
        <p className="muted">
          The agent is working. New steps appear as it goes.
        </p>
      )}
      {!working && steps.length === 0 && (
        <p className="muted">The agent has not worked on this claim yet.</p>
      )}
      <ol className="steps">
        {steps.map((step) => (
          <li key={step.id} className={`step step-${step.kind}`}>
            <div className="step-head">
              <span className="step-kind">{KIND_LABELS[step.kind]}</span>
              <span className="mono muted">{time(step.created_at)}</span>
            </div>
            <p className={step.kind.startsWith("tool") ? "code" : "prose"}>
              {step.text}
            </p>
          </li>
        ))}
      </ol>
    </section>
  );
}
