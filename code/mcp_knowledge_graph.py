"""
SovereignForge v1 - MCP Knowledge Graph
Graph-based knowledge representation for market intelligence and relationships
"""

import logging
import networkx as nx
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
import faiss
from typing import Dict, List, Optional, Tuple, Any, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from database import get_database
from trading import TradingEngine, TradingConfig
from gpu_accelerated_analysis import TimeSeriesFeatures
import asyncio
import json
import os

logging.basicConfig(level=logging.INFO)

@dataclass
class KnowledgeNode:
    """Node in the knowledge graph"""
    id: str
    node_type: str  # 'coin', 'exchange', 'regime', 'opportunity', 'correlation'
    properties: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[np.ndarray] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class KnowledgeEdge:
    """Edge in the knowledge graph"""
    source_id: str
    target_id: str
    edge_type: str  # 'trades_on', 'correlates_with', 'belongs_to_regime', 'creates_opportunity'
    properties: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    created_at: datetime = field(default_factory=datetime.utcnow)

@dataclass
class GraphQuery:
    """Query for the knowledge graph"""
    query_type: str  # 'semantic_search', 'relationship_query', 'pattern_matching'
    query_text: str
    filters: Dict[str, Any] = field(default_factory=dict)
    limit: int = 10

@dataclass
class QueryResult:
    """Result from a knowledge graph query"""
    nodes: List[KnowledgeNode]
    edges: List[KnowledgeEdge]
    relevance_scores: List[float]
    execution_time: float

class MarketKnowledgeGraph:
    """Graph-based knowledge representation for market intelligence"""

    def __init__(self, embedding_model: str = 'all-MiniLM-L6-v2'):
        self.graph = nx.MultiDiGraph()
        self.embedding_model = SentenceTransformer(embedding_model)
        self.vector_dimension = self.embedding_model.get_sentence_embedding_dimension()

        # FAISS index for vector search
        self.index = faiss.IndexFlatIP(self.vector_dimension)  # Inner product for cosine similarity
        self.node_id_to_index = {}  # Maps node IDs to FAISS indices
        self.index_to_node_id = {}  # Maps FAISS indices to node IDs

        # Node and edge storage
        self.nodes: Dict[str, KnowledgeNode] = {}
        self.edges: List[KnowledgeEdge] = []

        # Database connection
        self.db = get_database()

        logging.info(f"Initialized knowledge graph with {self.vector_dimension}D embeddings")

    async def add_coin_node(self, coin: str, properties: Dict[str, Any] = None) -> str:
        """Add a coin node to the graph"""
        node_id = f"coin_{coin}"
        if node_id in self.nodes:
            # Update existing node
            self.nodes[node_id].properties.update(properties or {})
            self.nodes[node_id].updated_at = datetime.utcnow()
        else:
            # Create new node
            node = KnowledgeNode(
                id=node_id,
                node_type='coin',
                properties=properties or {'symbol': coin, 'name': coin}
            )
            self.nodes[node_id] = node
            self.graph.add_node(node_id, **node.properties)

            # Generate embedding
            embedding_text = f"Cryptocurrency {coin} trading data and market analysis"
            node.embedding = self.embedding_model.encode(embedding_text)

            # Add to FAISS index
            self._add_to_index(node)

        return node_id

    async def add_exchange_node(self, exchange: str, properties: Dict[str, Any] = None) -> str:
        """Add an exchange node to the graph"""
        node_id = f"exchange_{exchange}"
        if node_id in self.nodes:
            self.nodes[node_id].properties.update(properties or {})
            self.nodes[node_id].updated_at = datetime.utcnow()
        else:
            node = KnowledgeNode(
                id=node_id,
                node_type='exchange',
                properties=properties or {'name': exchange, 'type': 'cryptocurrency_exchange'}
            )
            self.nodes[node_id] = node
            self.graph.add_node(node_id, **node.properties)

            # Generate embedding
            embedding_text = f"Cryptocurrency exchange {exchange} trading platform and market data"
            node.embedding = self.embedding_model.encode(embedding_text)

            # Add to FAISS index
            self._add_to_index(node)

        return node_id

    async def add_market_regime_node(self, regime: str, confidence: float, features: Dict[str, float]) -> str:
        """Add a market regime node"""
        node_id = f"regime_{regime}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        node = KnowledgeNode(
            id=node_id,
            node_type='regime',
            properties={
                'regime_type': regime,
                'confidence': confidence,
                'features': features,
                'timestamp': datetime.utcnow()
            }
        )
        self.nodes[node_id] = node
        self.graph.add_node(node_id, **node.properties)

        # Generate embedding
        embedding_text = f"Market regime {regime} with {confidence:.1%} confidence showing {', '.join(features.keys())}"
        node.embedding = self.embedding_model.encode(embedding_text)

        # Add to FAISS index
        self._add_to_index(node)

        return node_id

    async def add_arbitrage_opportunity_node(self, opportunity_data: Dict[str, Any]) -> str:
        """Add an arbitrage opportunity node"""
        opp_id = f"opportunity_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{hash(str(opportunity_data)) % 10000}"
        node = KnowledgeNode(
            id=opp_id,
            node_type='opportunity',
            properties=opportunity_data
        )
        self.nodes[opp_id] = node
        self.graph.add_node(opp_id, **node.properties)

        # Generate embedding
        coin = opportunity_data.get('coin', 'unknown')
        spread = opportunity_data.get('spread', 0)
        buy_ex = opportunity_data.get('buy_exchange', 'unknown')
        sell_ex = opportunity_data.get('sell_exchange', 'unknown')
        embedding_text = f"Arbitrage opportunity for {coin}: {spread:.2f}% spread between {buy_ex} and {sell_ex}"
        node.embedding = self.embedding_model.encode(embedding_text)

        # Add to FAISS index
        self._add_to_index(node)

        return opp_id

    async def add_relationship(self, source_id: str, target_id: str, edge_type: str,
                             properties: Dict[str, Any] = None, weight: float = 1.0):
        """Add a relationship between nodes"""
        if source_id not in self.nodes or target_id not in self.nodes:
            logging.warning(f"Cannot add relationship: nodes {source_id} or {target_id} not found")
            return

        edge = KnowledgeEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            properties=properties or {},
            weight=weight
        )
        self.edges.append(edge)
        self.graph.add_edge(source_id, target_id, key=edge_type, weight=weight, **(properties or {}))

    async def build_market_relationships(self):
        """Build relationships between market entities"""
        logging.info("Building market relationships...")

        # Coin-exchange relationships
        coins = ['XRP', 'XLM', 'HBAR', 'ALGO', 'ADA', 'LINK', 'IOTA', 'XDC', 'ONDO', 'VET', 'USDC', 'RLUSD']
        exchanges = ['binance', 'kraken', 'coinbase', 'bitfinex', 'gemini']

        for coin in coins:
            coin_node = await self.add_coin_node(coin)
            for exchange in exchanges:
                exchange_node = await self.add_exchange_node(exchange)
                await self.add_relationship(
                    coin_node, exchange_node, 'trades_on',
                    {'pair': f'{coin}/USDC', 'exchange': exchange}
                )

        # Coin correlation relationships (simplified)
        for i, coin1 in enumerate(coins):
            for coin2 in coins[i+1:]:
                # Simulate correlation based on coin properties
                correlation = np.random.uniform(0.1, 0.8)  # Random for demo
                if correlation > 0.3:  # Only add significant correlations
                    coin1_node = f"coin_{coin1}"
                    coin2_node = f"coin_{coin2}"
                    await self.add_relationship(
                        coin1_node, coin2_node, 'correlates_with',
                        {'correlation': correlation, 'strength': 'strong' if correlation > 0.6 else 'moderate'},
                        weight=correlation
                    )

        logging.info(f"Built relationships for {len(coins)} coins and {len(exchanges)} exchanges")

    async def semantic_search(self, query: str, limit: int = 10) -> QueryResult:
        """Perform semantic search on the knowledge graph"""
        start_time = datetime.utcnow()

        # Generate query embedding
        query_embedding = self.embedding_model.encode(query).astype(np.float32).reshape(1, -1)

        # Normalize for cosine similarity
        faiss.normalize_L2(query_embedding)

        # Search FAISS index
        if self.index.ntotal > 0:
            similarities, indices = self.index.search(query_embedding, min(limit, self.index.ntotal))

            # Get relevant nodes
            relevant_nodes = []
            relevance_scores = []
            for idx, score in zip(indices[0], similarities[0]):
                if idx != -1:  # Valid index
                    node_id = self.index_to_node_id.get(idx)
                    if node_id and node_id in self.nodes:
                        relevant_nodes.append(self.nodes[node_id])
                        relevance_scores.append(float(score))

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return QueryResult(
                nodes=relevant_nodes,
                edges=[],  # Could add edge search here
                relevance_scores=relevance_scores,
                execution_time=execution_time
            )
        else:
            return QueryResult(nodes=[], edges=[], relevance_scores=[], execution_time=0.0)

    async def find_related_entities(self, node_id: str, relationship_type: str = None,
                                  max_depth: int = 2) -> Dict[str, Any]:
        """Find related entities in the graph"""
        if node_id not in self.graph:
            return {'error': f'Node {node_id} not found'}

        # Find neighbors
        if relationship_type:
            neighbors = list(self.graph.neighbors(node_id))
            edges = []
            for neighbor in neighbors:
                edge_data = self.graph.get_edge_data(node_id, neighbor)
                if edge_data and relationship_type in edge_data:
                    edges.append({
                        'source': node_id,
                        'target': neighbor,
                        'type': relationship_type,
                        'properties': edge_data[relationship_type]
                    })
        else:
            # Get all relationships
            edges = []
            for source, target, key, data in self.graph.out_edges(node_id, keys=True, data=True):
                edges.append({
                    'source': source,
                    'target': target,
                    'type': key,
                    'properties': data
                })

        # Get node details
        related_nodes = {}
        for edge in edges:
            target_id = edge['target']
            if target_id in self.nodes:
                related_nodes[target_id] = self.nodes[target_id]

        return {
            'center_node': self.nodes.get(node_id),
            'related_nodes': list(related_nodes.values()),
            'relationships': edges,
            'total_relationships': len(edges)
        }

    async def analyze_market_structure(self) -> Dict[str, Any]:
        """Analyze the overall market structure"""
        analysis = {
            'total_nodes': len(self.nodes),
            'total_edges': len(self.edges),
            'node_types': {},
            'edge_types': {},
            'graph_density': 0.0,
            'centrality_measures': {}
        }

        # Count node types
        for node in self.nodes.values():
            analysis['node_types'][node.node_type] = analysis['node_types'].get(node.node_type, 0) + 1

        # Count edge types
        for edge in self.edges:
            analysis['edge_types'][edge.edge_type] = analysis['edge_types'].get(edge.edge_type, 0) + 1

        # Calculate graph density
        if len(self.nodes) > 1:
            max_edges = len(self.nodes) * (len(self.nodes) - 1)
            analysis['graph_density'] = len(self.edges) / max_edges if max_edges > 0 else 0

        # Calculate centrality measures (simplified)
        try:
            degree_centrality = nx.degree_centrality(self.graph)
            analysis['centrality_measures'] = {
                'top_nodes_by_degree': sorted(degree_centrality.items(), key=lambda x: x[1], reverse=True)[:5]
            }
        except:
            analysis['centrality_measures'] = {'error': 'Could not calculate centrality'}

        return analysis

    async def save_to_database(self):
        """Save the knowledge graph to database"""
        session = self.db.get_session()
        try:
            # Save nodes
            for node in self.nodes.values():
                # Convert numpy array to list for JSON storage
                embedding_list = node.embedding.tolist() if node.embedding is not None else None

                # Insert or update node
                session.execute("""
                    INSERT OR REPLACE INTO knowledge_nodes
                    (id, node_type, properties, embedding, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    node.id,
                    node.node_type,
                    json.dumps(node.properties),
                    json.dumps(embedding_list) if embedding_list else None,
                    node.created_at.isoformat(),
                    node.updated_at.isoformat()
                ))

            # Save edges
            for edge in self.edges:
                session.execute("""
                    INSERT OR REPLACE INTO knowledge_edges
                    (source_id, target_id, edge_type, properties, weight, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    edge.source_id,
                    edge.target_id,
                    edge.edge_type,
                    json.dumps(edge.properties),
                    edge.weight,
                    edge.created_at.isoformat()
                ))

            session.commit()
            logging.info(f"Saved {len(self.nodes)} nodes and {len(self.edges)} edges to database")

        except Exception as e:
            session.rollback()
            logging.error(f"Error saving to database: {e}")
        finally:
            session.close()

    async def load_from_database(self):
        """Load the knowledge graph from database"""
        session = self.db.get_session()
        try:
            # Load nodes
            nodes_result = session.execute("SELECT * FROM knowledge_nodes").fetchall()
            for row in nodes_result:
                embedding = np.array(json.loads(row[3])) if row[3] else None
                node = KnowledgeNode(
                    id=row[0],
                    node_type=row[1],
                    properties=json.loads(row[2]),
                    embedding=embedding,
                    created_at=datetime.fromisoformat(row[4]),
                    updated_at=datetime.fromisoformat(row[5])
                )
                self.nodes[row[0]] = node
                self.graph.add_node(row[0], **node.properties)

                # Add to FAISS index if embedding exists
                if embedding is not None:
                    self._add_to_index(node)

            # Load edges
            edges_result = session.execute("SELECT * FROM knowledge_edges").fetchall()
            for row in edges_result:
                edge = KnowledgeEdge(
                    source_id=row[0],
                    target_id=row[1],
                    edge_type=row[2],
                    properties=json.loads(row[3]),
                    weight=row[4],
                    created_at=datetime.fromisoformat(row[5])
                )
                self.edges.append(edge)
                self.graph.add_edge(row[0], row[1], key=row[2], weight=row[4], **edge.properties)

            logging.info(f"Loaded {len(self.nodes)} nodes and {len(self.edges)} edges from database")

        except Exception as e:
            logging.error(f"Error loading from database: {e}")
        finally:
            session.close()

    def _add_to_index(self, node: KnowledgeNode):
        """Add node to FAISS index"""
        if node.embedding is not None:
            # Normalize embedding for cosine similarity
            embedding = node.embedding.astype(np.float32).reshape(1, -1)
            faiss.normalize_L2(embedding)

            # Add to index
            index_id = self.index.ntotal
            self.index.add(embedding)
            self.node_id_to_index[node.id] = index_id
            self.index_to_node_id[index_id] = node.id

    async def get_market_intelligence(self, coin: str = None, exchange: str = None) -> Dict[str, Any]:
        """Get comprehensive market intelligence"""
        intelligence = {
            'market_overview': await self.analyze_market_structure(),
            'top_relationships': {},
            'recent_regimes': [],
            'active_opportunities': []
        }

        # Get top relationships for specific coin/exchange
        if coin:
            coin_node = f"coin_{coin}"
            intelligence['coin_relationships'] = await self.find_related_entities(coin_node)

        if exchange:
            exchange_node = f"exchange_{exchange}"
            intelligence['exchange_relationships'] = await self.find_related_entities(exchange_node)

        # Get recent market regimes
        regime_nodes = [node for node in self.nodes.values() if node.node_type == 'regime']
        regime_nodes.sort(key=lambda x: x.created_at, reverse=True)
        intelligence['recent_regimes'] = [
            {
                'regime': node.properties.get('regime_type'),
                'confidence': node.properties.get('confidence'),
                'timestamp': node.created_at.isoformat()
            } for node in regime_nodes[:5]
        ]

        # Get active opportunities
        opportunity_nodes = [node for node in self.nodes.values() if node.node_type == 'opportunity']
        opportunity_nodes.sort(key=lambda x: x.created_at, reverse=True)
        intelligence['active_opportunities'] = [
            {
                'coin': node.properties.get('coin'),
                'spread': node.properties.get('spread'),
                'exchanges': f"{node.properties.get('buy_exchange')} → {node.properties.get('sell_exchange')}",
                'timestamp': node.created_at.isoformat()
            } for node in opportunity_nodes[:10]
        ]

        return intelligence

class MCPKnowledgeGraphOrchestrator:
    """Orchestrates the MCP Knowledge Graph for SovereignForge"""

    def __init__(self, opensandbox_mode: bool = False):
        self.knowledge_graph = MarketKnowledgeGraph()
        self.db = get_database()
        self.initialized = False
        self.opensandbox_mode = opensandbox_mode
        self.container_network_disabled = True  # CEO-gated network access

    async def initialize_knowledge_graph(self):
        """Initialize the knowledge graph system"""
        logging.info("Initializing MCP Knowledge Graph...")

        # Create database tables if they don't exist
        await self._create_database_tables()

        # Load existing graph from database
        await self.knowledge_graph.load_from_database()

        # Build initial market relationships if graph is empty
        if len(self.knowledge_graph.nodes) == 0:
            await self.knowledge_graph.build_market_relationships()
            await self.knowledge_graph.save_to_database()

        self.initialized = True
        logging.info("MCP Knowledge Graph initialized")

    async def _create_database_tables(self):
        """Create database tables for knowledge graph"""
        session = self.db.get_session()
        try:
            # Create nodes table
            session.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_nodes (
                    id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    properties TEXT,
                    embedding TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Create edges table
            session.execute("""
                CREATE TABLE IF NOT EXISTS knowledge_edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    properties TEXT,
                    weight REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (source_id, target_id, edge_type)
                )
            """)

            session.commit()
            logging.info("Created knowledge graph database tables")

        except Exception as e:
            session.rollback()
            logging.error(f"Error creating database tables: {e}")
        finally:
            session.close()

    async def update_market_data(self, coin: str, exchange: str, features: TimeSeriesFeatures = None):
        """Update market data in the knowledge graph"""
        # Add/update coin and exchange nodes
        coin_node = await self.knowledge_graph.add_coin_node(coin)
        exchange_node = await self.knowledge_graph.add_exchange_node(exchange)

        # Add trading relationship
        await self.knowledge_graph.add_relationship(
            coin_node, exchange_node, 'trades_on',
            {'last_updated': datetime.utcnow().isoformat()}
        )

        # Add market regime if features available
        if features:
            from intelligent_trading_ai import MarketRegimeDetector
            regime_detector = MarketRegimeDetector()
            regime = regime_detector.detect_regime(features)

            regime_node = await self.knowledge_graph.add_market_regime_node(
                regime.regime, regime.confidence, regime.features
            )

            # Connect regime to coin
            await self.knowledge_graph.add_relationship(
                coin_node, regime_node, 'belongs_to_regime',
                {'confidence': regime.confidence}
            )

        # Save updates
        await self.knowledge_graph.save_to_database()

    async def query_market_intelligence(self, query: str) -> Dict[str, Any]:
        """Query the knowledge graph for market intelligence"""
        # Perform semantic search
        search_results = await self.knowledge_graph.semantic_search(query, limit=5)

        # Get market intelligence summary
        intelligence = await self.knowledge_graph.get_market_intelligence()

        return {
            'query': query,
            'search_results': {
                'nodes_found': len(search_results.nodes),
                'top_results': [
                    {
                        'id': node.id,
                        'type': node.node_type,
                        'properties': node.properties,
                        'relevance': score
                    } for node, score in zip(search_results.nodes, search_results.relevance_scores)
                ]
            },
            'market_intelligence': intelligence,
            'execution_time': search_results.execution_time
        }

    async def get_graph_statistics(self) -> Dict[str, Any]:
        """Get knowledge graph statistics"""
        return await self.knowledge_graph.analyze_market_structure()

# Global MCP orchestrator instance
mcp_orchestrator = None

def init_mcp_knowledge_graph() -> MCPKnowledgeGraphOrchestrator:
    """Initialize global MCP Knowledge Graph orchestrator"""
    global mcp_orchestrator
    if mcp_orchestrator is None:
        mcp_orchestrator = MCPKnowledgeGraphOrchestrator()
    return mcp_orchestrator

def get_mcp_orchestrator() -> MCPKnowledgeGraphOrchestrator:
    """Get global MCP Knowledge Graph orchestrator"""
    global mcp_orchestrator
    if mcp_orchestrator is None:
        raise RuntimeError("MCP Knowledge Graph not initialized. Call init_mcp_knowledge_graph() first.")
    return mcp_orchestrator

# Convenience functions
async def initialize_knowledge_graph():
    """Initialize the knowledge graph system"""
    orchestrator = get_mcp_orchestrator()
    await orchestrator.initialize_knowledge_graph()

async def query_intelligence(query: str) -> Dict[str, Any]:
    """Query market intelligence"""
    orchestrator = get_mcp_orchestrator()
    return await orchestrator.query_market_intelligence(query)

async def update_market_intelligence(coin: str, exchange: str, features=None):
    """Update market intelligence"""
    orchestrator = get_mcp_orchestrator()
    await orchestrator.update_market_data(coin, exchange, features)

def get_graph_stats() -> Dict[str, Any]:
    """Get graph statistics"""
    orchestrator = get_mcp_orchestrator()
    import asyncio
    # Create event loop if needed
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return {"error": "Cannot get stats while event loop is running"}
        else:
            return loop.run_until_complete(orchestrator.get_graph_statistics())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(orchestrator.get_graph_statistics())
        finally:
            loop.close()