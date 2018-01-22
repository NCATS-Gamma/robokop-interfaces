DRUG='Substance'
GENE='Gene'
PATHWAY='Pathway'
PROCESS='BiologicalProcess'
CELL='Cell'
ANATOMY='Anatomy'
PHENOTYPE='Phenotype'
DISEASE='Disease'
GENETIC_CONDITION='GeneticCondition'
DRUG_NAME = 'NAME.DRUG'
DISEASE_NAME = 'NAME.DISEASE'
UNSPECIFIED = 'UnspecifiedType'

node_types = set([DRUG, GENE, PATHWAY, PROCESS, CELL, ANATOMY, PHENOTYPE, DISEASE, GENETIC_CONDITION, DRUG_NAME, DISEASE_NAME, UNSPECIFIED])

type_codes = { 'S': DRUG, 'G':GENE, 'P':PROCESS, 'C':CELL, 'A':ANATOMY, 'T':PHENOTYPE, 'D':DISEASE, 'X':GENETIC_CONDITION , '?': UNSPECIFIED}
