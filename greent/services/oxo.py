import json
import requests
from greent.service import Service
from greent.graph_components import LabeledID
import time
from builder.question import LabeledID


class OXO(Service):
    """ Generic id translation service. Essentially a highly generic synonym finder. """

    def __init__(self, context):  # url="https://www.ebi.ac.uk/spot/oxo/api/search?size=500"):
        super(OXO, self).__init__("oxo", context)
        self.build_valid_curie_prefixes()

    def build_valid_curie_prefixes(self):
        """Query for the current valid list of input curies"""
        # size defaults to 40...
        url = "https://www.ebi.ac.uk/spot/oxo/api/datasources?size=10000"
        response = self.safeget(url)
        if response is None:
            #If we can't talk to oxo, we can't do much.
            raise Exception('Error Communicating with OXO')
        self.curies = set()
        for ds in response['_embedded']['datasources']:
            self.curies.add(ds['prefix'])
            self.curies.add(ds['prefix'].upper())
            self.curies.update(ds['alternatePrefix'])
            self.curies.update([x.upper() for x in ds['alternatePrefix']])
        self.curies.add('MESH')

    def is_valid_curie_prefix(self, cp):
        return cp != None and  (cp in self.curies or cp.upper() in self.curies)

    def request(self, url, obj):
        return requests.post(self.url,
                             data=json.dumps(obj, indent=2),
                             headers={"Content-Type": "application/json"})

    def query(self, ids, distance=2):
        #Occasionally, OXO will throw an exception in here, maybe due to load?
        #Calling with an unknown id just returns an empty set, so that's fine
        done = False
        num_tries = 0
        max_tries = 10
        wait_time = 5 # seconds
        while num_tries < max_tries:
            try:
                res = self.request(
                    url=self.url,
                    obj={
                        "ids": ids,
                        "mappingTarget": [],
                        "distance": str(distance),
                        "size": 10000
                    })
                if res.status_code == 200:
                    return res.json()
            except Exception as e:
                num_tries += 1
                time.sleep(wait_time)
        return None

    #TODO smush with the post version
    def safeget(self, url):
        #Occasionally, OXO will throw an exception in here, maybe due to load?
        #Calling with an unknown id just returns an empty set, so that's fine
        done = False
        num_tries = 0
        max_tries = 10
        wait_time = 5 # seconds
        while num_tries < max_tries:
            try:
                resp = requests.get(url)
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                num_tries += 1
                time.sleep(wait_time)
        return None

    #This is the main call into here.  It's what the synonymizer uses.
    def get_synonymous_curies(self, identifier, distance=2):
        synonyms = self.get_synonyms(identifier, distance)
        return set([x['curie'] for x in synonyms])

    #This is the new version of get_synonymous_curies that also returns labels
    def get_synonymous_curies_and_labels(self, identifier, distance=2):
        synonyms = self.get_synonyms(identifier, distance)
        return set([LabeledID(identifier=x['curie'], label=x['label']) for x in synonyms])

    def get_synonyms(self, identifier, distance=2):
        """ Find all synonyms for a curie for a given distance . """
        others = []
        response = self.query(ids=[identifier], distance=distance)
        try:
            searchResults = response['_embedded']['searchResults']
        except KeyError as e:
            raise e
        if len(searchResults) > 0 and searchResults[0]['queryId'] == identifier:
            others = searchResults[0]['mappingResponseList']
        return others

    #these two functions are used only to get icd9 codes for CDW.
    #But synonymization ought to be handling that now, so maybe we can stand to remove them?
    #TODO: Take out get_specific_synonym and get_specific_synonym_expanding
    def get_specific_synonym(self, identifier, prefix, distance=2):
        synonyms = self.get_synonyms(identifier, distance)
        return list(filter(lambda x: x['targetPrefix'] == prefix, synonyms))

    def get_specific_synonym_expanding(self, identifier, prefix):
        for i in range(1, 4):
            synonyms = self.get_specific_synonym(identifier, prefix, distance=i)
            if len(synonyms) > 0:
                return synonyms
        return []

"""These are no longer operant.  Will cut soon.
    def mesh_to_other(self, mesh_id):
        return self.get_synonyms(mesh_id)

    def compile_results(self, fname, ntype, searchResults):
        result = []
        for other in searchResults:
            result.append((KEdge('oxo', fname, is_synonym=True),
                           KNode(identifier=other['curie'], type=ntype)))
        return result

    def efo_to_doid(self, efo_node):
        searchResults = self.get_specific_synonym(efo_node.identifier, 'DOID')
        return self.compile_results('efo_to_doid', node_types.DISEASE, searchResults)

    def efo_to_umls(self, efo_node):
        searchResults = self.get_specific_synonym(efo_node.identifier, 'UMLS')
        return self.compile_results('efo_to_umls', node_types.DISEASE, searchResults)

    def umls_to_doid(self, umls_node):
        searchResults = self.get_specific_synonym(umls_node.identifier, 'DOID')
        return self.compile_results('umls_to_doid', node_types.DISEASE, searchResults)

    def ncit_to_hp(self, ncit_node):
        searchResults = self.get_specific_synonym(ncit_node.identifier, 'HP')
        return self.compile_results('efo_to_umls', node_types.DISEASE, searchResults)
    """
