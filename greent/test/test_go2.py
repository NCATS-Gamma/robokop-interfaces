import pytest
from greent.ontologies.go2 import GO2
from greent.servicecontext import ServiceContext
from greent import node_types
from greent.graph_components import KNode
from greent.util import Text

@pytest.fixture(scope='module')
def go2():
    return GO2(ServiceContext.create_context())

def test_biological_process(go2):
    #Mast Cell Chemotaxis
    go_id = 'GO:0002551'
    go_node=KNode(id=go_id)
    assert go2.is_biological_process(go_node), f"{go_id} is a biological process"
    assert not go2.is_cellular_component(go_node), f"{go_id} is not a cellular component"
    assert not go2.is_molecular_function(go_node), f"{go_id} is not a molecular function"

def test_cellular_component(go2):
    #Myelin Sheath
    go_id = 'GO:0043209'
    go_node=KNode(id=go_id)
    assert not go2.is_biological_process(go_node), f"{go_id} is not a biological process"
    assert go2.is_cellular_component(go_node), f"{go_id} is a cellular component"
    assert not go2.is_molecular_function(go_node), f"{go_id} is not a molecular function"

def test_molecular_function(go2):
    #FBXO Family Binding Protein
    go_id = 'GO:0098770'
    go_node=KNode(id=go_id)
    assert not go2.is_biological_process(go_node), f"{go_id} is not a biological process"
    assert not go2.is_cellular_component(go_node), f"{go_id} is not a cellular component"
    assert go2.is_molecular_function(go_node), f"{go_id} is a molecular function"

