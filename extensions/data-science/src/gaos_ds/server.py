from .catalog import get_resource, recommend, search_resources
from .recipes import list_recipes, render_recipe


def make_server(online=False):
    from fastmcp import FastMCP

    server = FastMCP("general-agent-data-science")

    @server.tool()
    def ds_search_resources(query: str = "", capability: str = "", limit: int = 20) -> list[dict]:
        """Search the curated offline model/method catalog. Capabilities: classification, regression,
        forecasting, exploration, statistics, explanation, causal, engineering, discovery, clustering.
        Resource cards distinguish runnable recipes, optional templates and catalog-only entries.
        """
        return search_resources(query, capability, limit)

    @server.tool()
    def ds_get_resource(resource_id: str) -> dict:
        """Get primary documentation, package, model license notes and available recipe IDs."""
        return get_resource(resource_id)

    @server.tool()
    def ds_recommend(capability: str, benchmark: str = "", gpu: bool = False) -> dict:
        """Suggest resources by the explicit public task capability and hardware. Not a performance ranking."""
        return recommend(capability, benchmark, gpu)

    @server.tool()
    def ds_list_recipes() -> list[dict]:
        """List portable analysis/model templates, parameter schemas, dependencies and actual validation status."""
        return list_recipes()

    @server.tool()
    def ds_render_recipe(recipe_id: str, parameters: dict) -> dict:
        """Validate parameters and return Python code plus a dependency preflight for execution in the task sandbox.
        Does not read data, install dependencies, run models or access evaluator labels.
        """
        return render_recipe(recipe_id, parameters)

    if online:

        @server.tool()
        def ds_search_hub(provider: str, kind: str, query: str, limit: int = 10) -> dict:
            """Read-only Hugging Face/Kaggle models or datasets metadata search; query is sent to that provider.
            Use for resource research when the task permits external resources; never send private data or labels.
            """
            from .providers import search_hub

            return search_hub(provider, kind, query, limit)

    return server
