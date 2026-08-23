from models.pre_clinical_tables import PreClinicalRnaSeq, PreClinicalCopyNumberVariation, PreClinicalMicroarray

pre_clinical_molecular_layers = {
    "RNA-seq": PreClinicalRnaSeq,
    "Copy Number Variation": PreClinicalCopyNumberVariation,
    "Microarray": PreClinicalMicroarray,    
}