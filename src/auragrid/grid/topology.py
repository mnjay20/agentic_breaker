import os
import csv
import re
from typing import Dict, List, Set, Tuple
from pydantic import BaseModel
from auragrid.config import settings

class NodeTopology(BaseModel):
    name: str
    voltage_kv: float
    is_critical_infrastructure: bool
    max_capacity_mw: float
    base_load_mw: float
    generation_mw: float
    taluk: str

class EdgeTopology(BaseModel):
    from_node: str
    to_node: str
    thermal_limit_mw: float
    breaker_id: str
    initial_state: int = 1  # 1 = Closed, 0 = Open

class GridTopology(BaseModel):
    city: str
    nodes: Dict[str, NodeTopology]
    edges: List[EdgeTopology]
    adjacency_list: Dict[str, List[str]] = {}

def clean_node_name(name: str) -> str:
    """Cleans substation names to be consistent and readable."""
    name = re.sub(r'\s+', ' ', name).strip()
    # Remove quotes
    name = name.replace('"', '').replace("'", "")
    return name

def get_substation_file(city: str) -> str:
    """Resolves the CSV filepath for a given city."""
    city_lower = city.lower()
    if "bengaluru" in city_lower or "bescom" in city_lower:
        filename = "Bengaluru Electrical Substations.csv"
    elif "bhopal" in city_lower:
        filename = "bhopal_substations.csv"
    elif "delhi" in city_lower:
        filename = "delhi_substations.csv"
    elif "jhansi" in city_lower:
        filename = "jhansi_substations.csv"
    elif "lucknow" in city_lower:
        filename = "lucknow_substations.csv"
    elif "pune" in city_lower:
        filename = "pune_substations.csv"
    else:
        # Fallback to Bengaluru as default
        filename = "Bengaluru Electrical Substations.csv"
    
    return os.path.join(settings.data_dir, filename)

def load_grid_topology(city: str) -> GridTopology:
    """
    Parses a city's substations CSV to dynamically build nodes.
    Then builds transmission lines (edges) using a deterministic hierarchical routing algorithm.
    """
    if city.lower() == "testcity":
        nodes = {
            "Node A": NodeTopology(
                name="Node A", voltage_kv=220.0, is_critical_infrastructure=False,
                max_capacity_mw=800.0, base_load_mw=400.0, generation_mw=0.0, taluk="Taluk 1"
            ),
            "Node B": NodeTopology(
                name="Node B", voltage_kv=220.0, is_critical_infrastructure=True,  # Hospital node
                max_capacity_mw=800.0, base_load_mw=300.0, generation_mw=0.0, taluk="Taluk 1"
            ),
            "Node C": NodeTopology(
                name="Node C", voltage_kv=400.0, is_critical_infrastructure=False,
                max_capacity_mw=1500.0, base_load_mw=100.0, generation_mw=900.0, taluk="Taluk 2" # Gen Node
            ),
            "Node D": NodeTopology(
                name="Node D", voltage_kv=66.0, is_critical_infrastructure=False,
                max_capacity_mw=200.0, base_load_mw=100.0, generation_mw=0.0, taluk="Taluk 2"
            ),
        }
        
        edges = [
            EdgeTopology(from_node="Node C", to_node="Node A", thermal_limit_mw=600.0, breaker_id="CB_C_A"),
            EdgeTopology(from_node="Node C", to_node="Node B", thermal_limit_mw=600.0, breaker_id="CB_C_B"),
            EdgeTopology(from_node="Node A", to_node="Node D", thermal_limit_mw=150.0, breaker_id="CB_A_D"),
        ]
        
        adj = {
            "Node A": ["Node C", "Node D"],
            "Node B": ["Node C"],
            "Node C": ["Node A", "Node B"],
            "Node D": ["Node A"],
        }
        
        return GridTopology(
            city=city,
            nodes=nodes,
            edges=edges,
            adjacency_list=adj
        )

    filepath = get_substation_file(city)
    
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Substation topology file not found: {filepath}")
    
    nodes: Dict[str, NodeTopology] = {}
    taluk_groups: Dict[str, List[NodeTopology]] = {}
    
    with open(filepath, mode='r', encoding='utf-8') as f:
        # Some CSVs may have BOM
        if f.read(1) != '\ufeff':
            f.seek(0)
        reader = csv.DictReader(f)
        for row in reader:
            raw_name = row.get("Name of Sub-Station") or row.get("Name of Sub-station")
            if not raw_name:
                continue
            name = clean_node_name(raw_name)
            
            # Parse voltage
            volt_str = row.get("Voltage Class (in kV)", "66")
            try:
                # Extracts numbers e.g. "220" or "SRS Peenya,220"
                volt_match = re.search(r'\d+', volt_str)
                voltage = float(volt_match.group()) if volt_match else 66.0
            except Exception:
                voltage = 66.0
                
            taluk = row.get("Taluk", "Unknown").strip()
            
            # Critical infrastructure heuristics
            name_lower = name.lower()
            is_critical = any(term in name_lower for term in [
                "hospital", "nimhans", "emergency", "airport", "water", "rail", "metro", "command", "police"
            ])
            
            # Assign capacity/generation/load defaults based on voltage class
            if voltage >= 400:
                max_capacity = 1500.0
                gen = 1000.0 if any(t in name_lower for t in ["plant", "dg", "solar", "wind", "thermal", "yelahanka"]) else 0.0
                load = 0.0 if gen > 0 else 800.0
            elif voltage >= 220:
                max_capacity = 800.0
                gen = 500.0 if any(t in name_lower for t in ["plant", "dg", "solar", "wind", "thermal", "yelahanka"]) else 0.0
                load = 0.0 if gen > 0 else 400.0
            else:
                max_capacity = 200.0
                gen = 0.0
                load = 100.0
                
            # Override for Yelahanka
            if "yelahanka" in name_lower and "plant" in name_lower:
                gen = 800.0
                load = 50.0
                
            node = NodeTopology(
                name=name,
                voltage_kv=voltage,
                is_critical_infrastructure=is_critical,
                max_capacity_mw=max_capacity,
                base_load_mw=load,
                generation_mw=gen,
                taluk=taluk
            )
            nodes[name] = node
            taluk_groups.setdefault(taluk, []).append(node)

    # Deterministic edge construction:
    # 1. Connect nodes within the same Taluk to the highest voltage node in that Taluk (the local Hub).
    # 2. Connect all local Hubs together in a sequence to form the transmission backbone.
    edges: List[EdgeTopology] = []
    hubs: List[NodeTopology] = []
    
    # Sort taluks deterministically
    sorted_taluks = sorted(taluk_groups.keys())
    for taluk in sorted_taluks:
        taluk_nodes = taluk_groups[taluk]
        # Find the highest voltage node in the taluk
        taluk_nodes.sort(key=lambda n: n.voltage_kv, reverse=True)
        hub = taluk_nodes[0]
        hubs.append(hub)
        
        # Connect other nodes in the taluk to the hub
        for leaf in taluk_nodes[1:]:
            # Determine thermal limit based on lowest voltage
            volt_min = min(hub.voltage_kv, leaf.voltage_kv)
            limit = 1200.0 if volt_min >= 400 else (600.0 if volt_min >= 220 else 150.0)
            
            breaker_id = f"CB_{hub.name.replace(' ', '_')}_{leaf.name.replace(' ', '_')}"
            edges.append(EdgeTopology(
                from_node=hub.name,
                to_node=leaf.name,
                thermal_limit_mw=limit,
                breaker_id=breaker_id
            ))
            
    # Connect the hubs in a backbone ring or chain
    for i in range(len(hubs)):
        n1 = hubs[i]
        n2 = hubs[(i + 1) % len(hubs)]
        if n1.name == n2.name:
            continue
        volt_min = min(n1.voltage_kv, n2.voltage_kv)
        limit = 1200.0 if volt_min >= 400 else (600.0 if volt_min >= 220 else 150.0)
        breaker_id = f"CB_{n1.name.replace(' ', '_')}_{n2.name.replace(' ', '_')}"
        edges.append(EdgeTopology(
            from_node=n1.name,
            to_node=n2.name,
            thermal_limit_mw=limit,
            breaker_id=breaker_id
        ))

    # Build adjacency list
    adj: Dict[str, List[str]] = {}
    for edge in edges:
        adj.setdefault(edge.from_node, []).append(edge.to_node)
        adj.setdefault(edge.to_node, []).append(edge.from_node)

    return GridTopology(
        city=city,
        nodes=nodes,
        edges=edges,
        adjacency_list=adj
    )
