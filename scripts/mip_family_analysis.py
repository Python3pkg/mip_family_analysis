#!/usr/bin/env python
# encoding: utf-8
"""
mip_family_analysis.py

Script for annotating which genetic models that are followed for variants in the mip pipeline.

Created by Måns Magnusson on 2013-01-31.
Copyright (c) 2013 __MyCompanyName__. All rights reserved.
"""

import sys
import os
import argparse
import shelve
import operator
from multiprocessing import JoinableQueue, Queue, Lock, cpu_count
from datetime import datetime

from Mip_Family_Analysis.Family import family_parser
from Mip_Family_Analysis.Variants import variant_parser
from Mip_Family_Analysis.Models import genetic_models, score_variants
from Mip_Family_Analysis.Utils import get_genes, variant_consumer


def main():
    parser = argparse.ArgumentParser(description="Parse different kind of ped files.")
    parser.add_argument('family_file', type=str, nargs=1, help='A pedigree file. Default is cmms format.')
    parser.add_argument('variant_file', type=str, nargs=1, help='A variant file.Default is vcf format')
    
    parser.add_argument('-v', '--verbose', action="store_true", help='Increase output verbosity.')
    
    parser.add_argument('-ga', '--gene_annotation', type=str, choices=['Ensembl', 'HGNC'], nargs=1, help='What gene annotation should be used, HGNC or Ensembl.')
    
    parser.add_argument('-o', '--output', type=str, nargs=1, help='Specify the path to a file where results should be stored.')

    parser.add_argument('-pos', '--position', action="store_true", help='If output should be sorted by position. Default is sorted on rank score')

    parser.add_argument('-tres', '--treshold', type=int, nargs=1, help='Specify the lowest rank score to be outputted.')
    
    args = parser.parse_args()
    
    gene_annotation = 'HGNC'
    
    # If gene annotation is manually given:
    
    if args.gene_annotation:
       gene_annotation = args.gene_annotation[0]
    
    new_headers = []    
        
    # Start by parsing at the pedigree file:
    family_type = 'cmms'
    family_file = args.family_file[0]
        
    my_family_parser = family_parser.FamilyParser(family_file, family_type)
    
    
    # Stupid thing but for now when we only look at one family
    my_family = my_family_parser.families.popitem()[1]

    preferred_models = my_family.models_of_inheritance
        
    # Check the variants:

    if args.verbose:
        print 'Parsing variants ...'
        print ''

    
    start_time_variant_parsing = datetime.now()
    
    var_file = args.variant_file[0]
    file_name, file_extension = os.path.splitext(var_file)
    
    individuals = []
    for ind in my_family.individuals:
        individuals.append(ind.individual_id)
        
    var_type = 'cmms'        
    header_line = []
    metadata = []
    
    # The task queue is where all jobs(in this case batches that represents variants in a region) is put
    # the consumers will then pick their jobs from this queue.
    tasks = JoinableQueue()
    # The consumers will put their results in the results queue
    results = Queue()
    # We will need a lock so that the consumers can print their results to screen
    lock = Lock()
    
    num_consumers = cpu_count() * 2
    consumers = [variant_consumer.VariantConsumer(lock, tasks, results, my_family) for i in xrange(num_consumers)]
    for w in consumers:
        w.start()
    
    num_jobs = 0
    with open(var_file, 'r') as f:
        
        beginning = True
        batch = [] # This is a list to store the variant lines of a batch
        current_genes = []  # These are lists to keep track of the regions that we look at
        new_region = []
        
        for line in f:
            line = line.rstrip()
            if line[:2] == '##':
                #This is the metadata information
                metadata.append(line)
            elif line[:1] == '#':
                header_line = line[1:].split('\t')
            else:
                #These are variant lines
                                
                splitted_line = line.split('\t')
                ensemble_entry = splitted_line[5]
                hgnc_entry = splitted_line[6]
                new_genes = get_genes.get_genes(hgnc_entry, 'HGNC')
                
                # If we look at the first variant, setup boundary conditions:
                if beginning:
                    current_genes = new_genes
                    beginning = False
                    batch.append(line) # Add variant line to batch
                # Now we have a new list of genes            
                else:
                    send = True
                    #Check if we are in a space between genes:
                    if len(new_genes) == 0:
                        if len(current_genes) == 0:
                            send = False
                    else:
                        for gene in new_genes:
                            if gene in current_genes:
                                send = False
                    if send:
                        # If there is an intergenetic region we do not look at the compounds.
                        compounds = True
                        if len(current_genes) == 0:
                            compunds = False
                        # The tasks are tuples like (variant_list, bool(if compounds))
                        tasks.put((variant_parser.variant_parser(batch, header_line, individuals), compounds))
                        num_jobs += 1
                        current_genes = new_genes
                        batch = [line]
                        # queue_reader_p.join() # Wait for the analysis to finish
                        # batch.append(line) # Add variant line to batch
                    else:
                        current_genes = list(set(current_genes) | set(new_genes))
                        batch.append(line) # Add variant line to batch
    # queue = Queue()
    # queue_reader_p = Process(target=check_variants, args=((queue),))
    # queue_reader_p.daemon = True
    # queue_reader_p.start()
    compounds = True
    if len(current_genes) == 0:
        compunds = False
    tasks.put((variant_parser.variant_parser(batch, header_line, individuals), compunds))
    num_jobs += 1
    # queue_reader_p.join() # Wait for the analysis to finish
    for i in xrange(num_consumers):
        tasks.put(None)
    
    # tasks.join()
    # 
    # while num_jobs:
    #     result = results.get()
    #     print 'Result: ', result
    #     num_jobs -= 1


    if args.verbose:
        print 'Variants done!. Time to parse variants: ', (datetime.now() - start_time_variant_parsing)
        print ''
    # 
    # # Add info about variant file:
    # new_headers = my_variant_parser.header_lines 
    # 
    # # Add new headers:
    # 
    # new_headers.append('Inheritance_model')
    # new_headers.append('Compounds')
    # new_headers.append('Rank_score')
    # 
    # 
    # if args.verbose:
    #     print 'Checking genetic models...'
    #     print ''
    # 
    # for data in my_variant_parser.metadata:
    #     print data
    # 
    # print '#'+'\t'.join(new_headers)
    # 
    # if not args.position:
    #     all_variants = {}
    # 
    # # Check the genetic models
    # 
    # jobs=[]
    # 
    # for chrom in my_variant_parser.chrom_shelves:
    #     
    #     shelve_directory = os.path.split(my_variant_parser.chrom_shelves[chrom])[0]
    #     current_shelve = my_variant_parser.chrom_shelves[chrom]
    #     
    #     p = multiprocessing.Process(target=check_variants, args=(current_shelve, my_family, gene_annotation, args, preferred_models))
    #     jobs.append(p)
    #     p.start()
    # 
    # for job in jobs:
    #     job.join()
    # 
    # # Print all variants:
    # 
    # for chrom in my_variant_parser.chrom_shelves:
    #     
    #     variants = []        
    #     variant_db = shelve.open(my_variant_parser.chrom_shelves[chrom])
    #     
    #     for var_id in variant_db:
    #         variants.append(variant_db[var_id])
    #         
    #     for variant in sorted(variants, key=lambda genetic_variant:genetic_variant.start):
    #         pass
    #         # print '\t'.join(variant.get_cmms_variant())
    # 
    # 
    #     os.remove(my_variant_parser.chrom_shelves[chrom])
    # os.removedirs(shelve_directory)
    # 
    # # Else print by rank score:
    # # if not args.position:
    # #     for variant in sorted(all_variants.iteritems(), key=lambda (k,v): int(operator.itemgetter(-1)(v)), reverse=True):
    # #         if args.treshold:
    # #             rank_score = int(variant[-1][-1])
    # #             if rank_score >= args.treshold[0]:
    # #                 print '\t'.join(variant[1])
    # #         else:
    #             # print '\t'.join(variant[1])
    # if args.verbose:
    #     print 'Finished analysis!'
    #     print 'Time for analysis', (datetime.now() - start_time_variant_parsing)



if __name__ == '__main__':
    main()

