#!/usr/bin/env python3
"""
SovereignForge - Training Knowledge Graph (Lightweight/Safe)

NetworkX + JSON-based knowledge graph for storing training metadata,
backtest results, and session history. Safe for local OpenSandbox execution
(no heavy ML dependencies like FAISS or sentence_transformers).
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import networkx as nx
    NX_AVAILABLE = True
except ImportError:
    NX_AVAILABLE = False
    logger.warning("NetworkX not available, knowledge graph disabled")


class TrainingKnowledgeGraph:
    """Lightweight knowledge graph for training metadata using NetworkX + JSON."""

    def __init__(self, graph_path: str = "data/training_knowledge_graph.json"):
        self.graph_path = Path(graph_path)
        self.graph_path.parent.mkdir(parents=True, exist_ok=True)

        if NX_AVAILABLE:
            self.graph = nx.DiGraph()
            self._load()
        else:
            self.graph = None

    def record_training_run(self, run_id: str, strategy: str, pair: str,
                            exchange: str, metrics: Dict[str, Any],
                            timestamp: str) -> None:
        """Record a training run as a node with edges to strategy/pair/exchange."""
        if self.graph is None:
            return

        # Create entity nodes if they don't exist
        for node_type, node_id in [
            ("strategy", strategy),
            ("pair", pair),
            ("exchange", exchange),
        ]:
            if not self.graph.has_node(node_id):
                self.graph.add_node(node_id, type=node_type)

        # Create training run node
        self.graph.add_node(run_id, type="training_run",
                            strategy=strategy, pair=pair, exchange=exchange,
                            timestamp=timestamp, **metrics)

        # Edges: run -> strategy, run -> pair, run -> exchange
        self.graph.add_edge(run_id, strategy, relation="uses_strategy")
        self.graph.add_edge(run_id, pair, relation="trains_pair")
        self.graph.add_edge(run_id, exchange, relation="trains_exchange")

        logger.debug(f"Recorded training run {run_id}")

    def record_backtest_result(self, run_id: str,
                               backtest_metrics: Dict[str, Any]) -> None:
        """Attach backtest results to an existing training run node."""
        if self.graph is None:
            return

        if self.graph.has_node(run_id):
            for key, value in backtest_metrics.items():
                self.graph.nodes[run_id][f"bt_{key}"] = value
        else:
            logger.warning(f"Run {run_id} not found in graph, creating new node")
            self.graph.add_node(run_id, type="training_run", **{
                f"bt_{k}": v for k, v in backtest_metrics.items()
            })

    def get_best_model(self, strategy: str, pair: str) -> Optional[Dict]:
        """Find the best-performing model for a strategy+pair by val_loss."""
        if self.graph is None:
            return None

        candidates = []
        for node, data in self.graph.nodes(data=True):
            if (data.get("type") == "training_run" and
                    data.get("strategy") == strategy and
                    data.get("pair") == pair and
                    "val_loss" in data):
                candidates.append({"run_id": node, **data})

        if not candidates:
            return None

        return min(candidates, key=lambda x: x.get("val_loss", float("inf")))

    def get_training_history(self, pair: Optional[str] = None,
                             exchange: Optional[str] = None) -> List[Dict]:
        """Get chronological training history, optionally filtered."""
        if self.graph is None:
            return []

        history = []
        for node, data in self.graph.nodes(data=True):
            if data.get("type") != "training_run":
                continue
            if pair and data.get("pair") != pair:
                continue
            if exchange and data.get("exchange") != exchange:
                continue
            history.append({"run_id": node, **data})

        history.sort(key=lambda x: x.get("timestamp", ""))
        return history

    def get_graph_stats(self) -> Dict:
        """Return summary statistics about the knowledge graph."""
        if self.graph is None:
            return {"status": "disabled"}

        type_counts = {}
        for _, data in self.graph.nodes(data=True):
            t = data.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": type_counts,
        }

    def save(self) -> None:
        """Persist graph to JSON file."""
        if self.graph is None:
            return

        data = nx.node_link_data(self.graph)
        # Convert any non-serializable values
        serializable = json.loads(json.dumps(data, default=str))

        with open(self.graph_path, "w") as f:
            json.dump(serializable, f, indent=2)

        logger.debug(f"Knowledge graph saved to {self.graph_path}")

    def _load(self) -> None:
        """Load graph from JSON if it exists."""
        if not self.graph_path.exists():
            return

        try:
            with open(self.graph_path, "r") as f:
                data = json.load(f)
            self.graph = nx.node_link_graph(data, directed=True)
            logger.info(f"Loaded knowledge graph: {self.graph.number_of_nodes()} nodes")
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Failed to load knowledge graph: {e}, starting fresh")
            self.graph = nx.DiGraph()
