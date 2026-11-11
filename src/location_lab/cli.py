import argparse
import json
from .core import Coordinate, MemoryBackend, Session
from .planner import command_plan
from .places import Place, PlaceStore, default_store, route_plan
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
    places = commands.add_parser("places", help="Manage private saved places; no device writes")
    places.add_argument("action", choices=("list", "save", "delete", "route"))
    places.add_argument("names", nargs="*")
    places.add_argument("--name")
    places.add_argument("--latitude", type=float)
    places.add_argument("--longitude", type=float)
    places.add_argument("--store", help="private JSON path; defaults outside the project")
    args = parser.parse_args(argv)
    if args.command == "scenario":
        print(json.dumps(run_scenario(args.name), ensure_ascii=False, indent=2))
        return 0
    if args.command == "places":
        try:
            store = PlaceStore(args.store or default_store())
            if args.action == "list":
                if args.names or args.name or args.latitude is not None or args.longitude is not None:
                    raise ValueError("list does not accept names or coordinates")
                result = {"mode": "local-place-store", "executed": False,
                          "hardware_verified": False,
                          "places": [place.to_dict() for place in store.list()]}
            elif args.action == "save":
                if args.names or not args.name or args.latitude is None or args.longitude is None:
                    raise ValueError("save requires --name, --latitude and --longitude")
                store.save(Place(args.name, Coordinate(args.latitude, args.longitude)))
                result = {"mode": "local-place-store", "executed": False,
                          "hardware_verified": False, "saved": args.name}
            elif args.action == "delete":
                if args.names or not args.name or args.latitude is not None or args.longitude is not None:
                    raise ValueError("delete requires only --name")
                result = {"mode": "local-place-store", "executed": False,
                          "hardware_verified": False, "deleted": store.delete(args.name)}
            else:
                if args.name or args.latitude is not None or args.longitude is not None:
                    raise ValueError("route accepts saved place names only")
                by_name = {place.name.casefold(): place for place in store.list()}
                if not args.names:
                    raise ValueError("route requires one or more saved place names")
                missing = [name for name in args.names if name.casefold() not in by_name]
                if missing:
                    raise ValueError("unknown saved place: " + missing[0])
                result = route_plan([by_name[name.casefold()] for name in args.names])
        except ValueError as exc:
            parser.error(str(exc))
        print(json.dumps(result, ensure_ascii=False, indent=2))
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
