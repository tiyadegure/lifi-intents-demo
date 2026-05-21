from .agent import interactive, LifAgent
import sys, json

if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        agent = LifAgent()
        agent.connect()
        try:
            from .agent import parse_intent
            intent = parse_intent(text)
            result = agent.get_quote(intent)
            print(json.dumps(result, indent=2))
        except ValueError as e:
            print(f"Error: {e}")
        finally:
            agent.close()
    else:
        interactive()
