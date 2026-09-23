import argparse
import json
import sys
from pathlib import Path

from .catalog import get_resource, recommend, search_resources
from .recipes import list_recipes, render_recipe


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Data-science resource tools; model execution belongs in a sandbox"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    catalog = sub.add_parser("catalog")
    catalog.add_argument("--query", default="")
    catalog.add_argument("--capability", default="")
    card = sub.add_parser("resource")
    card.add_argument("resource_id")
    suggestion = sub.add_parser("recommend")
    suggestion.add_argument("capability")
    suggestion.add_argument("--benchmark", default="")
    suggestion.add_argument("--gpu", action="store_true")
    sub.add_parser("recipes")
    render = sub.add_parser("render")
    render.add_argument("recipe_id")
    render.add_argument("--parameters", type=Path, required=True, help="JSON parameter file")
    render.add_argument("--code-only", action="store_true")
    search = sub.add_parser("search-hub", help="Explicit online metadata request")
    search.add_argument("provider", choices=["huggingface", "kaggle"])
    search.add_argument("kind", choices=["models", "datasets"])
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    serve = sub.add_parser("serve")
    serve.add_argument("--online", action="store_true", help="Expose online metadata search (off by default)")
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            from .server import make_server

            make_server(online=args.online).run(transport="stdio")
            return
        if args.command == "catalog":
            result = search_resources(args.query, args.capability, limit=50)
        elif args.command == "resource":
            result = get_resource(args.resource_id)
        elif args.command == "recommend":
            result = recommend(args.capability, args.benchmark, args.gpu)
        elif args.command == "recipes":
            result = list_recipes()
        elif args.command == "render":
            result = render_recipe(args.recipe_id, json.loads(args.parameters.read_text()))
            if args.code_only:
                print(result["code"])
                return
        else:
            from .providers import search_hub

            result = search_hub(args.provider, args.kind, args.query, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2) from None
