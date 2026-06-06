import os
from auragrid.grid.topology import load_grid_topology, clean_node_name

def test_clean_node_name():
    assert clean_node_name(' "SRS Peenya" ') == "SRS Peenya"
    assert clean_node_name("Koramangala   Residential") == "Koramangala Residential"

def test_load_topology_bengaluru():
    """Verify that we can load the Bengaluru topology from the CSV file."""
    topo = load_grid_topology("BESCOM_Bengaluru_Grid")
    
    # Check that we parsed nodes
    assert len(topo.nodes) > 0
    assert "Koramangala" in topo.nodes or "Koramangala*" in topo.nodes
    
    # Check that Hoody, Nelamangala, Peenya, Yelahanka are parsed
    any_yelahanka = any("yelahanka" in name.lower() for name in topo.nodes)
    assert any_yelahanka, "Should parse Yelahanka substation"
    
    # Check backbone and leaf connections
    assert len(topo.edges) > 0
    
    # Check critical infrastructure parsing
    critical_nodes = [name for name, node in topo.nodes.items() if node.is_critical_infrastructure]
    assert len(critical_nodes) > 0
    # Victoria Hospital should be marked critical
    victoria = [n for n in critical_nodes if "victoria" in n.lower()]
    assert len(victoria) > 0
