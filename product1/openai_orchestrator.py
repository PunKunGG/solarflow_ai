"""OpenAI orchestration layer.

The model is used for research planning / result interpretation. Numerical
physics is delegated to MEEP/Solcore/DEVSIM. The script uses the Responses API
and keeps external tool execution explicit.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from openai import OpenAI


SYSTEM = """
You are SolarFlow AI Research Orchestrator.
You do not invent scientific results. Physics simulations are authoritative
for numerical results. Your jobs are to: (1) propose next experiments from the
provided data, (2) flag missing assumptions, (3) summarize results, and (4)
produce a machine-readable design recommendation.
Always label surrogate/demo data as surrogate/demo.
"""


def analyze(results_path: str) -> str:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY in the environment before using OpenAI.")
    payload = json.loads(Path(results_path).read_text())
    client = OpenAI()
    resp = client.responses.create(
        model=os.getenv("OPENAI_MODEL", "gpt-5.6-luna"),
        input=[
            {"role": "system", "content": [{"type": "input_text", "text": SYSTEM}]},
            {"role": "user", "content": [{"type": "input_text", "text": json.dumps(payload, indent=2)}]},
        ],
    )
    return resp.output_text


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("results", help="JSON result file")
    args = ap.parse_args()
    print(analyze(args.results))
