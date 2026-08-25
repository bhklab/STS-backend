from models.tables import PreClinicalRnaSeq, PreClinicalCopyNumberVariation, PreClinicalMicroarray, PreClinicalTreatmentResponse
from models.tables import ClinicalRNA, ClinicalCNV, ClinicalMiRNA, ClinicalMutation, ClinicalRPPA, ClinicalMethylation

pre_clinical_molecular_layers = {
    "RNA-seq": PreClinicalRnaSeq,
    "Copy Number Variation": PreClinicalCopyNumberVariation,
    "Microarray": PreClinicalMicroarray,
}

pre_clinical_data_layers = {
    **pre_clinical_molecular_layers,
    "Treatment Response": PreClinicalTreatmentResponse,
}


clinical_molecular_layers = {
    "RNA-seq": ClinicalRNA,
    "Copy Number Variation": ClinicalCNV,
    "MiRNA": ClinicalMiRNA,
    "Mutation": ClinicalMutation,
    "RPPA": ClinicalRPPA,
    "Methylation": ClinicalMethylation,
}

clinical_data_layers = {
    **clinical_molecular_layers,
    # "Treatment Response": PreClinicalTreatmentResponse,
}