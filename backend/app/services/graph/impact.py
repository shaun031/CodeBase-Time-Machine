from uuid import UUID

import networkx as nx


class ImpactAnalysisService:
    @staticmethod
    def dependent_paths(
        graph: nx.DiGraph, target: UUID, depth: int
    ) -> list[tuple[UUID, list[UUID]]]:
        reverse = graph.reverse(copy=False)
        lengths = nx.single_source_shortest_path_length(reverse, target, cutoff=depth)
        result: list[tuple[UUID, list[UUID]]] = []
        for dependent, distance in lengths.items():
            if dependent == target or distance < 1:
                continue
            # The original dependency direction is dependent -> ... -> target.
            path = nx.shortest_path(graph, dependent, target)
            result.append((dependent, path))
        return sorted(result, key=lambda item: (len(item[1]), str(item[0])))
