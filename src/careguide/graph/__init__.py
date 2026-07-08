from careguide.graph.state import CareGuideState


__all__ = ["CareGuideGraph", "CareGuideState", "run_careguide"]


def __getattr__(name: str):
    if name == "CareGuideGraph":
        from careguide.graph.careguide_graph import CareGuideGraph

        return CareGuideGraph
    if name == "run_careguide":
        from careguide.graph.careguide_graph import run_careguide

        return run_careguide
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
