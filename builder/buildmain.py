from greent.graph_components import KNode, KEdge
from greent import node_types
from greent.util import LoggingUtil,Text
from greent.rosetta import Rosetta
from builder.userquery import UserQuery
import argparse
import networkx as nx
import logging
import sys
from neo4j.v1 import GraphDatabase
from importlib import import_module
from builder.lookup_utils import lookup_identifier
from collections import defaultdict
from builder.pathlex import tokenize_path
import calendar

logger = LoggingUtil.init_logging (__file__, logging.DEBUG)

def export_edge(tx,edge):
    """The approach of updating edges will be to erase an old one and replace it in whole.   There's no real
    reason to worry about preserving information from an old edge.
    What defines the edge are the identifiers of its nodes, and the source.function that created it."""
    aid = edge[0].identifier
    bid = edge[1].identifier
    ke  = edge[2]['object']
    #nn = len(ke.publications)
    #logger.debug(f'{aid},{bid},{ke.standard_predicate.label},{nn}')

    #Delete any old edge
    tx.run("MATCH (a {id: {aid}})-[r {source:{source}}]-(b {id:{bid}}) DELETE r",
                {'aid': aid, 'bid': bid, 'source': ke.edge_source} )
    #Now write the new edge....
    #note that we can't use the CURIE as the label, because the : in the curie screws up the cypher :(
    if ke.standard_predicate is None:
        logger.error('No standard predicate on the edge')
        logger.error(ke)
        print(ke)
    label='_'.join(ke.standard_predicate.identifier.split(':'))
    if label is None:
        print(ke)
        exit()
    #Following KG standardization here: https://docs.google.com/document/d/1TrvqJPe_HwmRJ5HCwZ7fsi9_mwGcwLOZ53Fnjo8Sh4E/
    # We are going to put original_predicate_label into "relation"
    # We are going to put standard_label into "predicate"
    tx.run (
        '''MATCH (a), (b) where a.id = {aid} AND b.id={bid} CREATE (a)-[r:%s {
           edge_source: {source}, 
           ctime:{ctime}, 
           predicate:{standard_label}, 
           predicate_id:{standard_id}, 
           relation:{original_predicate_label}, 
           relation_id:{original_predicate_id}, 
           publications:{publications}, url: {url},
           input_identifiers: {input}}]->(b) return r''' % (label,),
        {'aid': aid, 'bid': bid, 'source': ke.edge_source, 'ctime': calendar.timegm(ke.ctime.timetuple()),
         'standard_label': Text.snakify(ke.standard_predicate.label),
         'standard_id': ke.standard_predicate.identifier,
         'original_predicate_id': ke.original_predicate.identifier,
         'original_predicate_label': ke.original_predicate.label,
         'publication_count': len(ke.publications),
         'publications': ke.publications[:1000], 'url' : ke.url, 'input': ke.input_id}
    )
    if ke.standard_predicate.identifier == 'GAMMA:0':
        logger.error(f"Unable to map predicate for edge {ke.original_predicate}  {ke}")


def export_node(tx,node ):
    """Utility for writing updated nodes.  Goes in node?"""
    result = tx.run("MATCH (a {id: {id}}) RETURN a", {"id": node.identifier})
    original_record = result.peek()
    if not original_record:
        syns = list(node.synonyms)
        syns.sort()
        tx.run(
            "CREATE (a:%s {id: {id}, name: {name}, node_type: {node_type}, equivalent_identifiers: {syn}})"
            % (node.node_type),
            {"id": node.identifier, "name": node.label, "node_type": node.node_type, "syn": syns })
    else:
        original_node = original_record['a']
        if node.node_type not in original_node.labels:
            #Note: You can't use query parameterization on node labels in neo4j - UGH
            tx.run("MATCH (a {id: {identifier} }) SET a:%s" % (node.node_type,), identifier = node.identifier)
        new_syns = list(node.synonyms)
        new_syns.sort()
        if original_node['name'] != node.label or original_node['synonyms'] != new_syns:
            tx.run("MATCH (a {id: {identifier} }) SET a.name = {name}, a.equivalent_identifiers= {synonyms}",
                        identifier = node.identifier, name = node.label, synonyms = new_syns)

class KnowledgeGraph:
    def __init__(self, userquery, rosetta):
        """KnowledgeGraph is a local version of the query results. 
        After full processing, it gets pushed to neo4j.
        """
        self.graph = nx.MultiDiGraph()
        self.userquery = userquery
        self.rosetta = rosetta
        if not self.userquery.compile_query(self.rosetta):
            logger.error('Query fails. Exiting.')
            sys.exit(1)
        # node_map is a map from identifiers to the node associated.  It's useful because
        #  we are collapsing nodes along synonym edges, so each node might asked for in
        #  multiple different ways.
        self.node_map = {}

        #uri = 'bolt://localhost:7687'
        #self.driver = GraphDatabase.driver(uri, encrypted=False)
        # Use the same database connection as the type_graph.
        self.driver = self.rosetta.type_graph.driver
        
    def execute(self):
        """Execute the query that defines the graph"""
        logger.debug('Executing Query')
        logger.debug('Run Programs')
        for program in self.userquery.get_programs():
            result_graph = program.run_program( )
            self.add_edges(result_graph)
        logger.debug('Query Complete')

    def print_types(self):
        counts = defaultdict(int)
        for node in self.graph.nodes():
            counts[node.node_type] += 1
        for node_type in counts:
            logger.info('{}: {}'.format(node_type, counts[node_type]))

    def merge(self, source, target):
        """Source and target are both members of the graph, and we've found that they are
        synonyms.  Remove target, and attach all of target's edges to source"""
        logger.debug('Merging {} and {}'.format(source.identifier, target.identifier))
        source.add_synonym(target)
        nodes_from_target = self.graph.successors(target)
        for s in nodes_from_target:
            # b/c this is a multidigraph, this is actually a map where the edges are the values
            logger.debug('Node s: {}'.format(s))
            kedgemap = self.graph.get_edge_data(target, s)
            if kedgemap is None:
                logger.error('s?')
            for i in kedgemap.values():
                kedge = i['object']
                # The node being removed is the source in these edges, replace it
                kedge.subject_node = source
                self.graph.add_edge(source, s, object=kedge)
        nodes_to_target = self.graph.predecessors(target)
        for p in nodes_to_target:
            logger.debug('Node p: {}'.format(p))
            kedgemap = self.graph.get_edge_data(p, target)
            if kedgemap is None:
                logger.error('p?')
            for i in kedgemap.values():
                kedge = i['object']
                kedge.target_node = source
                self.graph.add_edge(p, source, object=kedge)
        self.graph.remove_node(target)
        # now, any synonym that was mapping to the old target should be remapped to source
        for k in self.node_map:
            if self.node_map[k] == target:
                self.node_map[k] = source

    def add_nonsynonymous_edge(self, edge, reverse_edges=False):
        # Found an edge between nodes. Add nodes if needed.
        source_node = self.add_or_find_node(edge.subject_node)
        target_node = self.add_or_find_node(edge.object_node)
        edge.subject_node = source_node
        edge.object_node = target_node
        # Now the nodes are translated to the canonical identifiers, make the edge
        # TODO: YUCK FIX
        if reverse_edges:
            logger.error("No reversing edges any more!")
            exit(1)
            edge.properties['reversed'] = True
            # We might already have this edge due to multiple "programs" running
            # Because it is a multigraph, graph[node][node] returns a map where the values are the edges
            try:
                potential_edges = [x['object'] for x in self.graph[target_node][source_node].values()]
            except KeyError:
                potential_edges = set()
            if edge not in potential_edges:
                self.graph.add_edge(target_node, source_node, object=edge)
                logger.debug('Edge: {}'.format(self.graph.get_edge_data(target_node, source_node)))
            else:
                logger.debug('Not adding repeating edge')
        else:
            edge.properties['reversed'] = False
            try:
                potential_edges = [x['object'] for x in self.graph[source_node][target_node].values()]
            except KeyError:
                potential_edges = set()
            if edge not in potential_edges:
                self.graph.add_edge(source_node, target_node, object=edge)
                logger.debug('Edge: {}'.format(self.graph.get_edge_data(source_node, target_node)))
            else:
                logger.debug('Not adding repeating edge')

    def add_edges(self, edge_list, reverse_edges=False):
        """Add a list of edges (and the associated nodes) to the graph."""
        for edge in edge_list:
            logger.debug('Edge: {} -> {}'.format(edge.subject_node.identifier, edge.object_node.identifier))
            self.add_nonsynonymous_edge(edge, reverse_edges)

    def find_node(self, node):
        """If node exists in graph, return it, otherwise, return None"""
        if node.identifier in self.node_map:
            return self.node_map[node.identifier]
        #We need to be less promiscuous here.   One thing that can happen is that OMIMs can unify what we consider
        # diseases and what we consider genes.  For now, we'll assume that our synonymization/normalization is working
        # well and # we don't have to sweat this.
        #for syn in node.synonyms:
        #    if syn in self.node_map:
        #        return self.node_map[syn]
        return None

    def add_or_find_node(self, node):
        """Find a node that already exists in the graph, checking for synonyms.
        If not found, create it & add to graph"""
        fnode = self.find_node(node)
        if fnode is not None:
            fnode.add_synonyms(node.synonyms)
            fnode.update_context(node.contexts)
            return fnode
        else:
            self.graph.add_node(node)
            self.node_map[node.identifier] = node
            for s in node.synonyms:
                self.node_map[s] = node
            return node

    def prune(self):
        """Recursively remove poorly connected nodes.  In particular, each (non-terminal) node
        must be connected to two different kinds of nodes."""
        # TODO, that is maybe a bit too much.  You can't have disease-gene-disease for instance !
        # But degree is not enough because you can have A and B both go to C but C doesn't go anywhere.
        # Probably need to interact with the query to decide whether this node is pruneable or not.
        logger.debug('Pruning Graph')
        removed = True
        # make the set of types that we don't want to prune.  These are the end points (both text and id versions).
        ttypes = self.userquery.get_terminal_types()
        if node_types.UNSPECIFIED in ttypes[1]:
            # Any kind of end node will match, so stop
            return
        keep_types = set()
        keep_types.update(ttypes[0])
        keep_types.update(ttypes[1])
        n_pruned = 0
        while removed:
            removed = False
            to_remove = []
            for node in self.graph.nodes():
                if node.node_type in keep_types:
                    continue
                # Graph is directed.  graph.neighbors only returns successors
                neighbors = self.graph.successors(node) + self.graph.predecessors(node)
                neighbor_types = set([neighbor.node_type for neighbor in neighbors])
                if len(neighbor_types) < 2:
                    # TODO: this is a little hacky and only covers some of the cases.
                    query_neighbor_types = self.userquery.get_neighbor_types(node.node_type)
                    graph_neighbor_type = list(neighbor_types)[0]
                    if (graph_neighbor_type, graph_neighbor_type) not in query_neighbor_types:
                        to_remove.append(node)
            for node in to_remove:
                removed = True
                n_pruned += 1
                self.graph.remove_node(node)
        logger.debug('Pruned {} nodes.'.format(n_pruned))

    def enhance(self):
        """Enhance nodes,edges with good labels and properties"""
        # TODO: it probably makes sense to push this stuff into the KNode itself
        logger.debug('Enhancing nodes with labels')
        for node in self.graph.nodes():
            from greent.util import Text
            if Text.get_curie(node.identifier) == 'DOID':
                print('NOOO {}'.format(node.identifier))
                exit()
            prepare_node_for_output(node, self.rosetta.core)

    def full_support(self,supporter, support_nodes):
        n_supported = 0
        support_edges = supporter.generate_all_edges(support_nodes)
        for support_edge in support_edges:
            self.add_nonsynonymous_edge(support_edge)
        n_supported = len(support_edges)
        return n_supported

    def path_support(self, supporter):
        n_supported = 0
        links_to_check = self.generate_links_from_paths()
        logger.info('Number of pairs to check: {}'.format(len(links_to_check)))
        print('Number of pairs to check: {}'.format(len(links_to_check)))
        for source, target in links_to_check:
            ids = [source.identifier, target.identifier]
            ids.sort()
            key = f"{supporter.__class__.__name__}({ids[0]},{ids[1]})"
            log_text = "  -- {key}"
            support_edge = self.rosetta.cache.get (key)
            if support_edge is not None:
                logger.info (f"cache hit: {key} {support_edge}")
            else:
                logger.info (f"exec op: {key}")
                support_edge = supporter.term_to_term(source, target)
                self.rosetta.cache.set (key, support_edge)
            if support_edge is not None:
                n_supported += 1
                if len(support_edge.publications)> 0:
                    logger.info('  -Adding support edge from {} to {}'.
                                      format(source.identifier, target.identifier))
                    self.add_nonsynonymous_edge(support_edge)
        return n_supported

    def support(self, support_module_names):
        """Look for extra information connecting nodes."""
        supporters = [import_module(module_name).get_supporter(self.rosetta.core)
                      for module_name in support_module_names]
        # TODO: how do we want to handle support edges
        # Questions: Are they new edges even if we have an edge already, or do we integrate
        #            Do we look for edges within a layer, e.g. to identify similar concepts
        #               That's a good idea, but might be a separate query?
        #            Do we only check for connections along a path?  That would help keep paths
        #               distinguishable, but we lose similarity stuff.
        #            Do we want to use knowledge to connect within (or across) layers.
        #               e.g. look for related diseases in  a disease layer.
        # Prototype version looks at each paths connecting ends, and tries to look for any more edges
        #  in each path. I think this is probably too constraining... but is more efficient
        #
        # Generate paths, (unique) edges along paths
        logger.debug('Building Support')
        for supporter in supporters:
            #n_supported = self.full_support(supporter)
            n_supported = self.path_support(supporter)
        logger.info('Support Completed.  Added {} edges.'.format(n_supported))

    def generate_all_links(self,nodelist=None):
        links_to_check = set()
        if nodelist is None:
            nodelist = self.graph.nodes()
        for i,node_i in enumerate(nodelist):
            for node_j in nodelist[i+1:]:
                links_to_check.add( (node_i, node_j) )
        return links_to_check


    def generate_links_from_paths(self):
        """This is going to assume that the first node is 0, which is bogus, but this is temp until support plan is figured out"""
        links_to_check = set()
        for program in self.userquery.get_programs():
            ancestors = defaultdict(set)
            current_nodes = set()
            program_number = program.program_number
            for node in self.graph.nodes():
                if 0 in node.contexts[program_number]: #start node
                    current_nodes.add(node)
            path = program.get_path_descriptor()
            nodenum = 0
            while nodenum in path:
                next_context,direction = path[nodenum]
                #logger.debug('Nodenum: {} {}'.format(nodenum,next_context))
                next_nodes = set()
                for node in current_nodes:
                    #logger.debug(' Current Node: {}'.format(node.identifier))
                    others = self.graph.successors(node) + self.graph.predecessors(node)
                    #else:
                    #if direction > 0:
                    #    others = self.graph.successors(node)
                    #else:
                    #    others = self.graph.predecessors(node)
                    for other in others:
                        #logger.debug('  Testing other: {} {}=?={}'.format(other.identifier, other.contexts[program_number], next_context))
                        if next_context in other.contexts[program_number]:
                            #logger.debug('Adding context for {}'.format(other))
                            ancestors[other].add(node)
                            ancestors[other].update(ancestors[node])
                            next_nodes.add(other)
                nodenum = next_context
                current_nodes = next_nodes
            for key in ancestors:
                #logger.debug("Ancestorkey {}".format(key))
                for a in ancestors[key]:
                    links_to_check.add( (key, a) )
        return links_to_check

    def export(self):
        """Export to neo4j database."""
        # TODO: lots of this should probably go in the KNode and KEdge objects?
        logger.info("Writing to neo4j")
        session = self.driver.session()
        # Now add all the nodes
        for node in self.graph.nodes():
            session.write_transaction(export_node,node)
        for edge in self.graph.edges(data=True):
            session.write_transaction(export_edge,edge)
        session.close()
        logger.info("Wrote {} nodes.".format(len(self.graph.nodes())))


# TODO: push to node, ...
def prepare_node_for_output(node, gt):
    logging.getLogger('application').debug('Prepare: {}'.format(node.identifier))
    logging.getLogger('application').debug('  Synonyms: {}'.format(' '.join(list(node.synonyms))))
    node.synonyms.update([mi['curie'] for mi in node.mesh_identifiers if mi['curie'] != ''])
    if node.node_type == node_types.DISEASE or node.node_type == node_types.GENETIC_CONDITION:
        if 'mondo_identifiers' in node.properties:
            node.synonyms.update(node.properties['mondo_identifiers'])
        try:
            node.label = gt.mondo.get_label(node.identifier)
        except:
            if node.label is None:
                node.label = node.identifier
    if node.label is None:
        if node.node_type == node_types.GENE and node.identifier.startswith('HGNC:'):
            node.label = gt.hgnc.get_name(node)
        elif node.node_type == node_types.GENE and node.identifier.upper().startswith('NCBIGENE:'):
            node.label = gt.hgnc.get_name(node)
        elif node.node_type == node_types.CELL and node.identifier.upper().startswith('CL:'):
            try:
                node.label = gt.uberongraph.cell_get_cellname(node.identifier)[0]['cellLabel']
            except:
                logging.getLogger('application').error('Error getting cell label for {}'.format(node.identifier))
                node.label = node.identifier
        else:
            node.label = node.identifier
    logging.getLogger('application').debug(node.label)


def run_query(querylist, supports, rosetta, prune=False):
    """Given a query, create a knowledge graph though querying external data sources.  Export the graph"""
    kgraph = KnowledgeGraph(querylist, rosetta)
    kgraph.execute()
    kgraph.print_types()
    if prune:
        kgraph.prune()
    kgraph.enhance()
    kgraph.support(supports)
    kgraph.export()


def generate_query(pathway, start_identifiers, end_identifiers=None):
    start, middle, end = pathway[0], pathway[1:-1], pathway[-1]
    query = UserQuery(start_identifiers, start.nodetype)
    print(start.nodetype)
    for transition in middle:
        print(transition)
        query.add_transition(transition.nodetype, transition.min_path_length, transition.max_path_length)
    print(end)
    query.add_transition(end.nodetype, end.min_path_length, end.max_path_length, end_values=end_identifiers)
    return query


def run(pathway, start_name, end_name,  supports, config):
    """Programmatic interface.  Pathway defined as in the command-line input.
       Arguments:
         pathway: A string defining the query.  See command line help for details
         start_name: The name of the entity at one end of the query
         end_name: The name of the entity at the other end of the query. Can be None.
         label: the label designating the result in neo4j
         supports: array strings designating support modules to apply
         config: Rosettta environment configuration. 
    """
    # TODO: move to a more structured pathway description (such as json)
    steps = tokenize_path(pathway)
    # start_type = node_types.type_codes[pathway[0]]
    start_type = steps[0].nodetype
    rosetta = setup(config)
    start_identifiers = lookup_identifier(start_name, start_type, rosetta.core)
    if end_name is not None:
        # end_type = node_types.type_codes[pathway[-1]]
        end_type = steps[-1].nodetype
        end_identifiers = lookup_identifier(end_name, end_type, rosetta.core)
    else:
        end_identifiers = None
    print("Start identifiers: " + '..'.join(start_identifiers))
    query = generate_query(steps, start_identifiers, end_identifiers)
    run_query(query, supports, rosetta, prune=False)


def setup(config):
    logger = logging.getLogger('application')
    logger.setLevel(level=logging.DEBUG)
    rosetta = Rosetta(greentConf=config,debug=True)
    return rosetta


helpstring = """Execute a query across all configured data sources.  The query is defined 
using the -p argument, which takes a string.  Each character in the string 
represents one high-level type of node that will be sequentially included 
denoted as:
S: Substance (Drug)
G: Gene
P: Process (Pathway)
C: Cell Type
A: Anatomical Feature
T: Phenotype
D: Disease
X: Genetic Condition
?: Unspecified Node

It is also possible to specify indirect transitions by including 
parenthetical values between these letters containing the number of 
allowed type transitions. A default (direct) transition would
be denoted (1-1), but it is not necessary to include between
every node.

Examples:
    DGX        Go directly from Disease, to Gene, to Genetic Condition.
    D(1-2)X    Go from Disease to Genetic Condition, either directly (1)
               or via another node (of any type) in between
    SGPCATD    Construct a Clinical Outcome Pathway, moving from a Drug 
               to a Gene to a Process to a Cell Type to an Anatomical 
               Feature to a Phenotype to a Disease. Each with no 
               intermediary nodes
    SG(2-5)D   Go from a Drug to a Gene, through 2 to 5 other transitions, and 
               to a Disease.
"""


def main():
    parser = argparse.ArgumentParser(description=helpstring,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-s', '--support', help='Name of the support system',
                        action='append',
                        #choices=['chemotext', 'chemotext2', 'cdw'],
                        choices=['omnicorp', 'chemotext', 'cdw'],
                        required=True)
    parser.add_argument('-p', '--pathway', help='Defines the query pathway (see description). Cannot be used with -q',
                        required=False)
    parser.add_argument('-q', '--question',
                        help='Shortcut for certain questions (1=Disease/GeneticCondition, 2=COP, 3=COP ending in Phenotype). Cannot be used with -p',
                        choices=[1, 2, 3],
                        required=False,
                        type=int)
    parser.add_argument('-c', '--config', help='Rosetta environment configuration file.',
                        default='greent.conf')
    parser.add_argument('--start', help='Text to initiate query', required=True)
    parser.add_argument('--end', help='Text to finalize query', required=False)
    args = parser.parse_args()
    pathway = None
    if args.pathway is not None and args.question is not None:
        print('Cannot specify both question and pathway. Exiting.')
        sys.exit(1)
    if args.question is not None:
        if args.question == 1:
            pathway = 'DGX'
            if args.end is not None:
                print('--end argument not supported for question 1.  Ignoring')
        elif args.question == 2:
            pathway = 'SGPCATD'
        elif args.question == 3:
            pathway = 'SGPCAT'
        if args.question in (2, 3):
            if args.end is None:
                print('--end required for question 2. Exiting')
                sys.exit(1)
    else:
        pathway = args.pathway
    run(pathway, args.start, args.end, args.support, config=args.config)


if __name__ == '__main__':
    main()
