import subprocess
from pathlib import Path
import pandas as pd
import time
import os
import re
import concurrent.futures

from libs.miRgeEssential import UID


def alignPlusParse(bwtExec, iter_number, pdDataFrame):
    """
    ALIGN TO BOWTIE, PARSE SAM FILE AND UPDATE THE DATAFRAME
    """
    colnames = list(pdDataFrame.columns)
    colToAct = 1 + int(iter_number)
    bowtie = subprocess.run(str(bwtExec), shell=True, check=True, stdout=subprocess.PIPE, text=True, stderr=subprocess.PIPE, universal_newlines=True)
    if bowtie.returncode==0:
        bwtOut = bowtie.stdout
        bwtErr = bowtie.stderr
    for srow in bwtOut.split('\n'):
        if not srow.startswith('@'):
            sam_line = srow.split('\t')
            if sam_line != ['']:
                if sam_line[2] != "*":
                    pdDataFrame.at[sam_line[0], colnames[colToAct]] = sam_line[2]
                    pdDataFrame.at[sam_line[0], colnames[0]] = 1
                    #if iter_number == 0 or iter_number == 8:
                    #    print(sam_line)
    return pdDataFrame



def bwtAlign(args,pdDataFrame,workDir,ref_db):
    """
    THIS FUNCTION COLLECTS DATAFRAME AND USER ARGUMENTS TO MAP TO VARIOUS DATABASES USING BOWTIE. CALLED FIRST AND ONCE. 
    """
    global threads
    threads = args.threads
    begningTime = time.perf_counter()
    bwtCommand = Path(args.bowtie_path)/"bowtie " if args.bowtie_path else "bowtie "
    bwtInput = Path(workDir)/"bwtInput.fasta"
    print("Alignment in progress ...")
    indexNames = ['_mirna_', '_hairpin_', '_mature_trna', '_pre_trna', '_snorna', '_rrna', '_ncrna_others', '_mrna', '_mirna_', '_spike-in']
    parameters = [' -n 0 -f --norc -S --threads ', ' -n 1 -f --norc -S --threads ', ' -v 1 -f -a --best --strata --norc -S --threads ', ' -v 0 -f -a --best --strata --norc -S --threads ', ' -n 1 -f --norc -S --threads ', ' -n 1 -f --norc -S --threads ', ' -n 1 -f --norc -S --threads ', ' -n 0 -f --norc -S --threads ', ' -5 1 -3 2 -v 2 -f --norc --best -S --threads ', ' -n 0 -f --norc -S --threads ']
    if args.spikeIn:
        iterations = 10
    else:
        iterations = 9
    for bwt_iter in range(iterations):
        if bwt_iter == 0:
            with open(bwtInput, 'w') as wseq:
                for sequences in (pdDataFrame.index[pdDataFrame.index.str.len() < 26]):
                    wseq.write(">"+str(sequences)+"\n")
                    wseq.write(str(sequences)+"\n")

            indexName  = str(args.organism_name) + str(indexNames[bwt_iter]) + str(ref_db)
            indexFiles = Path(args.libraries_path)/args.organism_name/"index.Libs"/indexName
            bwtExec = str(bwtCommand) + " " + str(indexFiles) + str(parameters[bwt_iter]) + str(args.threads) + " " + str(bwtInput) 
            alignPlusParse(bwtExec, bwt_iter, pdDataFrame)
        
        elif bwt_iter == 1:
            with open(bwtInput, 'w') as wseq: 
                for sequences in (pdDataFrame.index[pdDataFrame.index.str.len() > 25]):
                    wseq.write(">"+str(sequences)+"\n")
                    wseq.write(str(sequences)+"\n")

            indexName  = str(args.organism_name) + str(indexNames[bwt_iter]) + str(ref_db)
            indexFiles = Path(args.libraries_path)/args.organism_name/"index.Libs"/indexName
            bwtExec = str(bwtCommand) + " " + str(indexFiles) + str(parameters[bwt_iter]) + str(args.threads) + " " + str(bwtInput) 
            alignPlusParse(bwtExec, bwt_iter, pdDataFrame)

        else:
            if bwt_iter == 8: 
                indexName  = str(args.organism_name) + str(indexNames[bwt_iter]) + str(ref_db)
            else:
                indexName  = str(args.organism_name) + str(indexNames[bwt_iter])
            if bwt_iter == 3:
                with open(bwtInput, 'w') as wseq:
                    for sequences in (pdDataFrame.index[pdDataFrame.annotFlag.eq(0)]):
                        try:
                            footer = sequences[:(re.search('T{3,}$', sequences).span(0)[0])]
                            wseq.write(">"+str(sequences)+"\n")
                            wseq.write(str(footer)+"\n")
                        except AttributeError:
                            pass
            else:
                with open(bwtInput, 'w') as wseq:
                    for sequences in (pdDataFrame.index[pdDataFrame.annotFlag.eq(0)]):
                        wseq.write(">"+str(sequences)+"\n")
                        wseq.write(str(sequences)+"\n")

            indexFiles = Path(args.libraries_path)/args.organism_name/"index.Libs"/indexName
            bwtExec = str(bwtCommand) + " " + str(indexFiles) + str(parameters[bwt_iter]) + str(args.threads) + " " + str(bwtInput) 
            alignPlusParse(bwtExec, bwt_iter, pdDataFrame)
    finish = time.perf_counter()
    if not args.spikeIn:
        pdDataFrame = pdDataFrame.drop(columns=['spike-in'])
    
    os.remove(bwtInput)
    pdDataFrame = pdDataFrame.fillna('')
    print(f'Alignment completed in {round(finish-begningTime, 4)} second(s)\n')
    return pdDataFrame
