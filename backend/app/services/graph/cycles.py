from dataclasses import dataclass
from uuid import UUID

import networkx as nx


@dataclass(frozen=True)
class CycleGroup:
    members: list[UUID]
    edges: list[tuple[UUID, UUID]]


class CycleDetectionService:
    @staticmethod
    def find(graph: nx.DiGraph) -> list[CycleGroup]:
        groups: list[CycleGroup] = []
        for component in nx.strongly_connected_components(graph):
            if len(component) < 2 and not any(graph.has_edge(node, node) for node in component):
                continue
            members = sorted(component, key=str)
            internal = sorted(
                (
                    (source, target)
                    for source, target in graph.edges()
                    if source in component and target in component
                ),
                key=lambda item: (str(item[0]), str(item[1])),
            )
            groups.append(CycleGroup(members, internal))
        return sorted(groups, key=lambda group: (-len(group.members), str(group.members[0])))
