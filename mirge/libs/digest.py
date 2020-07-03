#!/usr/bin/env python
import dnaio
import os
import time
import concurrent.futures
import pandas as pd
from pathlib import Path

from cutadapt.adapters import warn_duplicate_adapters
from cutadapt.parser import AdapterParser
from cutadapt.modifiers import (LengthTagModifier, SuffixRemover, PrefixSuffixAdder,
        ZeroCapper, QualityTrimmer, UnconditionalCutter, NEndTrimmer, AdapterCutter,
        PairedAdapterCutterError, PairedAdapterCutter, NextseqQualityTrimmer, Shortener)



def parse_cutoffs(s):
    """
    FUNCTION ADOPTED FROM CUTADAPT 2.7, TO CREATE INPUT PARAMETERS ACCORDING TO CUTADAPT.
    Parse a string INT[,INT] into a two-element list of integers
    >>> parse_cutoffs("5") => [0, 5]
    >>> parse_cutoffs("6,7") => [6, 7]
    """
    try:
        cutoffs = [int(value) for value in s.split(",")]
    except ValueError as e:
        exit("Quality cutoff value not recognized: {}".format(e))
    
    if len(cutoffs) == 1:
        cutoffs = [0, cutoffs[0]]
    elif len(cutoffs) != 2:
        exit("Expected one value or two values separated by comma for the quality cutoff")
    return cutoffs



def add_unconditional_cutters(pipeline_add, cut1):
    """
    FUNCTION ADOPTED FROM CUTADAPT 2.7, TO CREATE INPUT PARAMETERS ACCORDING TO CUTADAPT.
    """
    for i, cut_arg in enumerate([cut1]):
        # cut_arg is a list
        if not cut_arg:
            continue
        if len(cut_arg) > 2:
            exit("You cannot remove bases from more than two ends.")
        if len(cut_arg) == 2 and cut_arg[0] * cut_arg[1] > 0:
            exit("You cannot remove bases from the same end twice.")
        for c in cut_arg:
            if c == 0:
               continue
            if i == 0:  # R1
                pipeline_add(UnconditionalCutter(c))



def stipulate(args):
    """
    REQUIRED TO CREATE ITERABLE FUNCTIONS TO RUN IN CUTADAPT 2.7. THIS FUNCTION IS CALLED ONLY ONE TIME. 
    """
    modifiers=[]
    pipeline_add = modifiers.append
    adapter_parser = AdapterParser(
            max_error_rate=args.error_rate,
            min_overlap=args.overlap,
            read_wildcards=args.match_read_wildcards,
            adapter_wildcards=args.match_adapter_wildcards,
            indels=args.indels,
         )
    adapters = adapter_parser.parse_multi(args.adapters)
    warn_duplicate_adapters(adapters)

    if args.nextseq_trim is not None:
        pipeline_add(NextseqQualityTrimmer(args.nextseq_trim, args.phred64))
    if args.quality_cutoff is not None:
        cutoffs = parse_cutoffs(args.quality_cutoff)
        pipeline_add(QualityTrimmer(cutoffs[0], cutoffs[1], args.phred64))

    adapter_cutter = None
    if adapters:
        adapter_cutter = AdapterCutter(adapters, args.times, args.action)
        pipeline_add(adapter_cutter)
    if args.trim_n:
        pipeline_add(NEndTrimmer())
    add_unconditional_cutters(pipeline_add, args.cut)
        
    return modifiers



def baking(args, inFileArray, inFileBaseArray, workDir):
    """
    THIS FUNCTION IS CALLED FIRST FROM THE miRge3.0. 
    THIS FUNCTION PREPARES FUNCTIONS REQUIRED TO RUN IN CUTADAPT 2.7 AND PARSE ONE FILE AT A TIME. 
    """
    global ingredients, threads, buffer_size, trimmed_reads, fasta, fileTowriteFasta, min_len, umi
    numlines=10000
    umi = args.uniq_mol_ids
    fasta = args.fasta
    threads = args.threads
    buffer_size = args.buffer_size
    min_len = args.minimum_length
    ingredients = stipulate(args)
    df_mirged=pd.DataFrame()
    complete_set=pd.DataFrame()
    begningTime = time.perf_counter()
    sampleReadCounts={}
    trimmedReadCounts={}
    trimmedReadCountsUnique={}
    runlogFile = Path(workDir)/"run.log"
    outlog = open(str(runlogFile),"a+")
    for index, FQfile in enumerate(inFileArray):
        start = time.perf_counter()
        finish2=finish3=finish4=finish5=0
        with concurrent.futures.ProcessPoolExecutor(max_workers=threads) as executor:
            with dnaio.open(FQfile, mode='r') as readers:
                readobj=[]
                count=trimmed=0
                completeDict = {}
                for reads in readers:
                    count+=1
                    readobj.append(reads)
                    if len(readobj) == 1000000:
                        future = [executor.submit(cutadapt, readobj[i:i+numlines]) for i in range(0, len(readobj), numlines)] # sending bunch of reads (#1000000) for parallel execution
                        for fqres_pairs in concurrent.futures.as_completed(future): 
                            for each_list in fqres_pairs.result(): # retreving results from parallel execution
                                varx = list(each_list)
                                if varx[0] in completeDict: # Collapsing, i.e., counting the occurance of each read for each data 
                                    completeDict[varx[0]] += int(varx[1])
                                    trimmed+=int(varx[1])
                                else:
                                    completeDict[varx[0]] = int(varx[1])
                                    trimmed+=int(varx[1])
                        readobj=[]
                future=[]
                future.extend([executor.submit(cutadapt, readobj[i:i+numlines]) for i in range(0, len(readobj), numlines)]) # sending remaining reads for parallel execution
                for fqres_pairs in concurrent.futures.as_completed(future):
                    for each_list in fqres_pairs.result(): # retreving results from parallel execution
                        varx = list(each_list)
                        if varx[0] in completeDict: # Collapsing, i.e., counting the occurance of each read for each data 
                            completeDict[varx[0]] += int(varx[1])
                            trimmed+=int(varx[1])
                        else:
                            completeDict[varx[0]] = int(varx[1])
                            trimmed+=int(varx[1])
                readobj=[]
        digestReadCounts = {inFileBaseArray[index]:trimmed}
        uniqTrimmedReads = {inFileBaseArray[index]:len(completeDict)}
        #digestReadCounts = {inFileBaseArray[index]:sum(completeDict.values())}
        inputReadCounts = {inFileBaseArray[index]:count}
        sampleReadCounts.update(inputReadCounts)
        trimmedReadCounts.update(digestReadCounts)
        trimmedReadCountsUnique.update(uniqTrimmedReads)
        finish2 = time.perf_counter()
        if not args.quiet:
            print(f'Cutadapt finished for file {inFileBaseArray[index]} in {round(finish2-start, 4)} second(s)')
        outlog.write(f'Cutadapt finished for file {inFileBaseArray[index]} in {round(finish2-start, 4)} second(s)\n')
        """
        CREATING PANDAS MATRIX FOR ALL THE SAMPLES THAT CAME THROUGH 
        WILL BE EDITED TO A FUNCTION, ONCE UMI COMES IN PICTURE
        """
        if args.tcf_out:
            fno = str(inFileBaseArray[index]) + '.trim.collapse.fa'
            fo_tcf = Path(workDir)/fno
            header_count = 1
            with open(fo_tcf,'w') as fo:
                for seqs in sorted(completeDict, key=completeDict.get, reverse=True):
                    head_r = ">seq"+str(header_count)+"_"+str(completeDict[seqs])+"\n"
                    fo.write(head_r)
                    fo.write(str(seqs)+"\n")
                    header_count+=1

        collapsed_df = pd.DataFrame(list(completeDict.items()), columns=['Sequence', inFileBaseArray[index]])
        collapsed_df.set_index('Sequence',inplace = True)
        if len(inFileBaseArray) == 1:
            complete_set = collapsed_df 
            collapsed_df = pd.DataFrame() 
        elif len(inFileBaseArray) > 1:
            complete_set = complete_set.join(collapsed_df, how='outer')
            collapsed_df = pd.DataFrame() 
        complete_set = complete_set.fillna(0).astype(int)
        finish3 = time.perf_counter()
        if not args.quiet:
            print(f'Collapsing finished for file {inFileBaseArray[index]} in {round(finish3-finish2, 4)} second(s)\n')
        outlog.write(f'Collapsing finished for file {inFileBaseArray[index]} in {round(finish3-finish2, 4)} second(s)\n')
    
    #complete_set['SeqLength'] = complete_set.index.str.len()
    initialFlags = ['exact miRNA','hairpin miRNA','mature tRNA','primary tRNA','snoRNA','rRNA','ncrna others','mRNA','isomiR miRNA','spike-in'] # keeping other columns ready for next assignment
    complete_set = complete_set.assign(**dict.fromkeys(initialFlags, ''))
    annotFlags = ['annotFlag']
    complete_set = complete_set.assign(**dict.fromkeys(annotFlags, '0'))
    #lengthCol = ['SeqLength']
    finalColumns = annotFlags +initialFlags + inFileBaseArray # rearranging the columns as we want  
    #finalColumns = lengthCol + annotFlags +initialFlags + inFileBaseArray # rearranging the columns as we want  
    complete_set = complete_set.reindex(columns=finalColumns)
    complete_set = complete_set.astype({"annotFlag": int})
    finish4 = time.perf_counter()
    if not args.quiet:
        print(f'Matrix creation finished in {round(finish4-finish3, 4)} second(s)\n')
    outlog.write(f'Matrix creation finished in {round(finish4-finish3, 4)} second(s)\n')
    EndTime = time.perf_counter()
    if not args.quiet:
        print(f'Data pre-processing completed in {round(EndTime-begningTime, 4)} second(s)\n')
    outlog.write(f'\nData pre-processing completed in {round(EndTime-begningTime, 4)} second(s)\n\n')
    outlog.close()
    return(complete_set, sampleReadCounts, trimmedReadCounts, trimmedReadCountsUnique)


def UMIParser(s, f, b):
    #front = s[:n]
    if int(b) != 0:
        center = s[f:-b]
    else:
        center = s[f:]
    #end = s[-n:]
    return (center)
    #return (front, center, end)


# THIS IS WHERE EVERYTHIHNG HAPPENS - Modifiers, filters etc...
def cutadapt(fq):
    readDict={}
    for fqreads in fq:
        matches=[]
        for modifier in ingredients:
            fqreads = modifier(fqreads, matches)
        if umi:
            if int(len(fqreads.sequence)) >= int(min_len):
                #print(str(fqreads.sequence)+"\n")
                umi_cut = umi.split(",")
                seq = UMIParser(fqreads.sequence, int(umi_cut[0]), int(umi_cut[1]))
                #start,seq,end = UMIParser(fqreads.sequence, 4)
                #print(str(start)+str(end)+"\n")
                if int(len(seq)) >= int(min_len):
                    if str(seq) in readDict:
                        readDict[str(seq)]+=1
                    else:
                        readDict[str(seq)]=1
        else:
            if int(len(fqreads.sequence)) >= int(min_len):
                if str(fqreads.sequence) in readDict:
                    readDict[str(fqreads.sequence)]+=1
                else:
                    readDict[str(fqreads.sequence)]=1
    trimmed_pairs = list(readDict.items())
    return trimmed_pairs
