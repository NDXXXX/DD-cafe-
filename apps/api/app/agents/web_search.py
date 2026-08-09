from dataclasses import dataclass

from ddgs import DDGS


@dataclass(frozen=True)
class WebSearchResult:
    title: str
    url: str
    snippet: str


class WebSearchTool:
    trigger_words = ("网上", "搜索", "最新", "今天", "新闻")

    def should_search(self, query: str) -> bool:
        return any(word in query for word in self.trigger_words)

    def search(self, query: str, limit: int = 3) -> list[WebSearchResult]:
        results = DDGS().text(query, max_results=limit)
        return [
            WebSearchResult(
                title=str(result.get("title", "")),
                url=str(result.get("href", "")),
                snippet=str(result.get("body", "")),
            )
            for result in results
        ]
