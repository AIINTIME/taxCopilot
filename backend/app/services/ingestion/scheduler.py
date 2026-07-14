"""Entrypoint for periodic ingestion runs (statutory source re-scraping)."""


async def run_scheduled_ingestion() -> None:
    raise NotImplementedError(
        "TODO: trigger orchestration.graphs.ingestion_graph for each "
        "allow-listed source on a schedule"
    )
