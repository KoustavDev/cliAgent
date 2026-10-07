"""Tools, safety checks, or lifecycle hooks provided by this module.

The public objects below validate inputs, perform their operation, and return
structured results without changing the surrounding application workflow.
"""
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
from duckduckgo_search import DDGS


class WebSearchParams(BaseModel):
    """Represent websearchparams state and behavior."""
    query: str = Field(..., description="Search query")
    max_results: int = Field(
        10,
        ge=1,
        le=20,
        description="Maximum results to return (default: 10)",
    )


class WebSearchTool(Tool):
    """Represent websearchtool state and behavior."""
    name = "web_search"
    description = "Search the web for information. Returns search results with titles, URLs and snippets"
    kind = ToolKind.NETWORK
    schema = WebSearchParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        # Step 1: Submit the query and format the search provider response.
        """Perform the execute operation and return its result."""
        params = WebSearchParams(**invocation.params)

        try:
            results = DDGS().text(
                params.query,
                region="us-en",
                safesearch="off",
                timelimit="y",
                page=1,
                backend="auto",
            )
        except Exception as e:
            return ToolResult.error_result(f"Search failed: {e}")

        if not results:
            return ToolResult.success_result(
                f"No results found for: {params.query}",
                metadata={
                    "results": 0,
                },
            )

        output_lines = [f"Search results for: {params.query}"]

        for i, result in enumerate(results, start=1):
            output_lines.append(f"{i}. Title: {result['title']}")
            output_lines.append(f"   URL: {result['href']}")
            if result.get("body"):
                output_lines.append(f"   Snippet: {result['body']}")

            output_lines.append("")

        return ToolResult.success_result(
            "\n".join(output_lines),
            metadata={
                "results": len(results),
            },
        )
