from __future__ import annotations

from dockline.agent import Agent
from dockline.client import ClearbayClient
from dockline.score import load_cases, score_case, summarize


async def run_evals(base_url: str | None = None, ids: list[str] | None = None) -> dict:
    cases = load_cases()
    if ids:
        want = set(ids)
        cases = [c for c in cases if c["id"] in want]
    agent = Agent(ClearbayClient(base_url=base_url))
    results = []
    for case in cases:
        if case.get("mutate"):
            continue
        trace = await agent.run(case["tenant"], case["prompt"])
        results.append(score_case(case, trace))
    return {"summary": summarize(results), "results": results}
