from .agent import interactive, LifAgent
import sys, json

if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        agent = LifAgent()

        if text == "doctor":
            report = agent.doctor()
            print(json.dumps(report, indent=2))
        elif text.startswith("safe "):
            from .agent import parse_intent_with_policy
            agent.connect()
            try:
                intent, policy = parse_intent_with_policy(text[5:])
                result = agent.safe_verdict_trace(intent, policy)
                print(json.dumps(result, default=lambda o: o.__dict__, indent=2))
            except ValueError as e:
                print(f"Error: {e}")
            finally:
                agent.close()
        else:
            from .agent import parse_intent
            agent.connect()
            try:
                intent = parse_intent(text)
                result = agent.get_quote(intent)
                print(json.dumps(result, indent=2))
            except ValueError as e:
                print(f"Error: {e}")
            finally:
                agent.close()
    else:
        interactive()
