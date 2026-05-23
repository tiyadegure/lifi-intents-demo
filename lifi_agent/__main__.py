from .agent import interactive, LifAgent
from rich.console import Console
from rich.syntax import Syntax
import sys, json

console = Console()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:])
        agent = LifAgent()

        if text == "doctor":
            report = agent.doctor()
            json_str = json.dumps(report, indent=2)
            console.print(Syntax(json_str, "json", theme="monokai"))
        elif text.startswith("explain "):
            try:
                result = agent.explain(text[8:])
                json_str = json.dumps(result, indent=2)
                console.print(Syntax(json_str, "json", theme="monokai"))
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
        elif text.startswith("safe "):
            from .agent import parse_intent_with_policy
            agent.connect()
            try:
                intent, policy = parse_intent_with_policy(text[5:])
                result = agent.safe_verdict_trace(intent, policy)
                json_str = json.dumps(result, default=lambda o: o.__dict__, indent=2)
                console.print(Syntax(json_str, "json", theme="monokai"))
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
            finally:
                agent.close()
        else:
            from .agent import parse_intent
            agent.connect()
            try:
                intent = parse_intent(text)
                result = agent.get_quote(intent)
                json_str = json.dumps(result, indent=2)
                console.print(Syntax(json_str, "json", theme="monokai"))
            except ValueError as e:
                console.print(f"[red]Error:[/red] {e}")
            finally:
                agent.close()
    else:
        interactive()
