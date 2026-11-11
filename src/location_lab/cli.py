import argparse
import json
from .core import Coordinate, MemoryBackend, Session
from .planner import command_plan
from .scenarios import SCENARIOS, run_scenario


def main(argv=None):
    parser = argparse.ArgumentParser(description="Location Lab: offline prototype, no device writes")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Set and clear an in-memory location")
    plan = commands.add_parser("plan", help="Print a command plan; never execute")
    plan.add_argument("action", choices=("set", "clear"))
    for sub in (demo, plan):
        sub.add_argument("--latitude", type=float)
        sub.add_argument("--longitude", type=float)
    scenario = commands.add_parser("scenario", help="Run a deterministic offline fault exercise")
    scenario.add_argument("name", choices=SCENARIOS)
    args = parser.parse_args(argv)
    if args.command == "scenario":
        print(json.dumps(run_scenario(args.name), ensure_ascii=False, indent=2))
        return 0
    try:
        needs_point = args.command == "demo" or args.action == "set"
        if needs_point:
            if args.latitude is None or args.longitude is None:
                raise ValueError("both --latitude and --longitude are required")
            point = Coordinate(args.latitude, args.longitude)
        else:
            if args.latitude is not None or args.longitude is not None:
                raise ValueError("clear does not accept coordinates")
            point = None
        if args.command == "plan":
            result = command_plan(args.action, point)
        else:
            session = Session(MemoryBackend())
            session.set_location(point)
            active = session.state.value
            session.clear_location()
            result = {"mode": "mock", "hardware_verified": False,
                      "states": [active, session.state.value]}
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0
