from __future__ import annotations

import argparse
import json

from .agent import AsterRowAgent


def main():
    parser = argparse.ArgumentParser(description="Aster & Row support agent")
    parser.add_argument("--session-id", default="default")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--message", help="Ask the support agent a question")
    args = parser.parse_args()

    agent = AsterRowAgent()
    if args.message:
        result = agent.respond(args.message, session_id=args.session_id, debug=args.debug)
        print(json.dumps({
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "handoff": result.get("handoff", False),
            "tool_calls": result.get("tool_calls", []),
            "debug": result.get("debug", {}),
        }, indent=2))
        return

    print("Aster & Row Support Agent")
    print("Type 'quit' to exit.")
    while True:
        user_input = input("You> ").strip()
        if user_input.lower() in {"quit", "exit"}:
            break
        result = agent.respond(user_input, session_id=args.session_id, debug=args.debug)
        print("Agent>", result["answer"])
        if result.get("sources"):
            print("Sources:", ", ".join(result["sources"]))
        if result.get("handoff"):
            print("Recommended handoff: yes")
        else:
            print("Recommended handoff: no")


if __name__ == "__main__":
    main()
