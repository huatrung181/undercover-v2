"""The backend for the end-to-end tests, with a scripted model in place of a real one.

The agent, its tools and the backend all run as they do in production; only the
model's replies are scripted, by claim id.
"""

import re
import time
from typing import Any

import uvicorn
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent import main as agent
from backend.db import seed

PORT = 8001
DECISIONS = {
    "CLM-1001": ("approve", 420.0),
    "CLM-1002": ("approve", 1150.0),
    "CLM-1005": ("decline", 0.0),
}


def tool_call(name: str, args: dict[str, Any]) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": name}])


def script(claim_id: str) -> list[AIMessage]:
    """The model's replies for one claim, turn by turn."""
    verdict, payout = DECISIONS.get(claim_id, ("refer", 0.0))
    replies = [
        tool_call("get_claim", {"claim_id": claim_id}),
        tool_call(
            "record_decision",
            {
                "claim_id": claim_id,
                "decision": verdict,
                "payout": payout,
                "reason": f"The scripted agent decided to {verdict} this claim.",
                "policy_section": "Section 10, How we work out your payment",
            },
        ),
    ]
    if verdict == "approve":
        replies.append(tool_call("pay_claim", {"claim_id": claim_id, "amount": payout}))
    return [*replies, AIMessage(content=f"Claim {claim_id} is done.")]


class ScriptedModel(BaseChatModel):
    """Replies from the script for the claim named in the first user message."""

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        time.sleep(0.5)
        request = next(m for m in messages if isinstance(m, HumanMessage))
        claim_id = re.findall(r"CLM-\d+", request.text)[0]
        turn = sum(isinstance(m, AIMessage) for m in messages)
        return ChatResult(generations=[ChatGeneration(message=script(claim_id)[turn])])


if __name__ == "__main__":
    seed()
    agent.BACKEND_URL = f"http://127.0.0.1:{PORT}"
    agent.model = ScriptedModel
    uvicorn.run("backend.main:app", port=PORT)
