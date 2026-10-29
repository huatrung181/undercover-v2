"""Run the UnderCover Agent on one claim: uv run -m agent CLM-1001"""

import sys
import time

from agent.main import backend


def main(claim_id: str) -> None:
    """Start the agent on a claim, print its steps and then its decision."""
    with backend() as client:
        client.post(f"/api/claims/{claim_id}/runs").raise_for_status()
        shown = 0
        while True:
            claim = client.get(f"/api/claims/{claim_id}").json()
            steps = client.get(f"/api/claims/{claim_id}/steps").json()
            for step in steps[shown:]:
                print(f"[{step['kind']}] {step['text']}")
            shown = len(steps)
            if claim["status"] != "in_progress":
                break
            time.sleep(1)
    print(f"\nStatus: {claim['status']}")
    if decision := claim["decision"]:
        print(f"Decision: {decision['decision']}, ${decision['payout']:,.2f}")
        print(f"Section: {decision['policy_section']}")
        print(f"Reason: {decision['reason']}")


if __name__ == "__main__":
    main(sys.argv[1])
