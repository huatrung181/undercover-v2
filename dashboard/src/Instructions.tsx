import { getInstructions } from "./api";
import { usePolling } from "./hooks";

export function Instructions() {
  const { data, error } = usePolling(getInstructions, 0);

  return (
    <>
      <h1>Agent instructions</h1>
      <p className="muted">
        The UnderCover Agent works from these instructions on every claim. They
        are read only.
      </p>
      {error && <p className="alert">The backend is not responding.</p>}
      {data && (
        <section className="panel">
          <p className="prose">{data.instructions}</p>
        </section>
      )}
    </>
  );
}
