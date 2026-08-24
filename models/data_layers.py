from models.pre_clinical_tables import PreClinicalRnaSeq, PreClinicalCopyNumberVariation, PreClinicalMicroarray, PreClinicalTreatmentResponse

pre_clinical_molecular_layers = {
    "RNA-seq": PreClinicalRnaSeq,
    "Copy Number Variation": PreClinicalCopyNumberVariation,
    "Microarray": PreClinicalMicroarray,
}

pre_clinical_data_layers = {
    **pre_clinical_molecular_layers,
    "Treatment Response": PreClinicalTreatmentResponse,
}