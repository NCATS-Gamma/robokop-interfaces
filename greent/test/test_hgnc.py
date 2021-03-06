import pytest
from greent.graph_components import KNode
from greent.services.hgnc import HGNC
from greent.servicecontext import ServiceContext
from greent import node_types
from greent.util import Text

@pytest.fixture(scope='module')
def hgnc():
    hgnc = HGNC(ServiceContext.create_context())
    return hgnc

#the HGNC class should no longer be used, replaced by initial or service synonyms

'''
The function being tested has been removed.
def test_ncbi_to_uniprot(hgnc):
    hgnc = HGNC( ServiceContext.create_context() )
    input_knode = KNode( 'NCBIGENE:3815' , node_type = node_types.GENE )
    results = hgnc.ncbigene_to_uniprotkb( input_knode )
    assert(len(results) == 1)
    node = results[0][1]
    assert node.type == node_types.GENE
    assert Text.get_curie(node.identifier).upper() == 'UNIPROTKB'
    assert Text.un_curie(node.identifier) == 'P10721'
    '''

def _test_synonym(hgnc):
    ncbigene = 'NCBIGENE:3815'
    syns = hgnc.get_synonyms(ncbigene)
    curies = [Text.get_curie(s.identifier).upper() for s in syns]
    for c in ['NCBIGENE','OMIM','UNIPROTKB','ENSEMBL','HGNC']:
        assert c in curies

def _test_uniprot(hgnc):
    uniprot='UniProtKB:Q96RI1'
    syns = [s.identifier for s  in hgnc.get_synonyms(uniprot) ]
    assert 'HGNC:7967' in syns

def _test_rnacentral(hgnc):
    rna='RNAcentral:URS00000C7662_9606'
    syns = [s.identifier for s in hgnc.get_synonyms(rna)]
