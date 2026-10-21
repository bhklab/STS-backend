"""
A small, read-only GraphQL schema over the portal's database.

It is used in two places:
  1. Mounted at /api/graphql so people can explore it in the browser (GraphiQL).
  2. By the AI assistant (routes/assistant.py), which writes GraphQL queries
     against this schema to answer user questions.

There are no mutations, so nothing here can change the database.

Every table in the database is reachable, and each foreign key can be followed
as a nested field (e.g. treatmentResponses { cellLine { ... } drug { ... } }).

The molecular tables are very large (clinical_methylation alone has ~100M rows),
so their top-level queries require a gene or sample filter, and every list is
capped at MAX_ROWS rows.
"""

import json
from urllib.parse import urlencode
from urllib.request import urlopen

import strawberry
from fastapi import Depends
from sqlalchemy import or_
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from database_session import get_db_session
from routes.dataset import find_available_data_layers
from models.tables import (
    Dataset,
    PreClinicalGene,
    Drugs,
    # Clinical tables
    ClinicalSample,
    ClinicalAntigen,
    ClinicalProbe,
    ClinicalRNA,
    ClinicalMutation,
    ClinicalCNV,
    ClinicalRPPA,
    ClinicalMiRNA,
    ClinicalMethylation,
    ClinicalSlide,
    ClinicalTile,
    ClinicalEmbedding,
    # Pre-clinical tables
    PreClinicalCellLine,
    PreClinicalCellLineInfo,
    PreClinicalSample,
    PreClinicalTreatmentResponse,
    PreClinicalRnaSeq,
    PreClinicalMicroarray,
    PreClinicalCopyNumberVariation,
)

# Never return more than this many rows from a single list field.
MAX_ROWS = 500

# AnnotationDB knows drug synonyms (e.g. "adriamycin" -> Doxorubicin) and is
# where the portal's drug annotations come from.
ANNOTATIONDB_COMPOUND_URL = "https://annotationdb.bhklab.ca/compound/many"
ANNOTATIONDB_TIMEOUT_SECONDS = 5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def clamp_limit(limit: int) -> int:
    """Keep the requested row limit between 1 and MAX_ROWS."""
    return max(1, min(limit, MAX_ROWS))


def find_compounds_in_annotationdb(name: str) -> list[dict]:
    """
    Ask AnnotationDB which compounds match a drug name or synonym.
    Each result has (among other fields) "cid" and "title".
    Returns an empty list if AnnotationDB can't be reached, so callers can
    fall back to searching the local database.
    """
    parameters = urlencode(
        {
            "compound": name,
            "format": "json",
            # Skip the large extra sections; we only need cid and title.
            "bioassay": "false",
            "mechanism": "false",
            "indication": "false",
            "toxicity": "false",
            "golden_bioassay": "false",
        }
    )
    try:
        with urlopen(
            f"{ANNOTATIONDB_COMPOUND_URL}?{parameters}",
            timeout=ANNOTATIONDB_TIMEOUT_SECONDS,
        ) as response:
            return json.load(response)
    except (OSError, ValueError):
        # OSError covers network errors and timeouts; ValueError covers bad JSON.
        return []


def get_session(info: Info):
    """The database session for this request (set in get_graphql_context)."""
    return info.context["session"]


def find_gene_ids(session, gene: str) -> list[str]:
    """
    Turn a gene symbol (e.g. 'TP53') or Ensembl id (e.g. 'ENSG00000141510')
    into the list of matching Ensembl ids. Uses an exact match so that
    'TP53' does not also match 'TP53BP1'.
    """
    rows = (
        session.query(PreClinicalGene.id)
        .filter(or_(PreClinicalGene.id == gene, PreClinicalGene.name == gene))
        .all()
    )
    return [row.id for row in rows]


def require_a_filter(**filters):
    """
    Raise an error unless at least one of the given filters was set.
    Used by queries over the huge molecular tables.
    """
    if all(value is None for value in filters.values()):
        names = " or ".join(filters.keys())
        raise ValueError(f"This table is very large: please filter by {names}.")


def filter_by_clinical_dataset(query, model, dataset_id: int | None):
    """Keep only rows whose clinical sample belongs to the given dataset."""
    if dataset_id is None:
        return query
    return query.join(ClinicalSample, model.sample_id == ClinicalSample.id).filter(
        ClinicalSample.dataset_id == dataset_id
    )


def filter_by_pre_clinical_dataset(query, model, dataset_id: int | None):
    """Keep only rows whose pre-clinical sample belongs to the given dataset."""
    if dataset_id is None:
        return query
    return query.join(
        PreClinicalSample, model.sample_id == PreClinicalSample.id
    ).filter(PreClinicalSample.dataset_id == dataset_id)


# ---------------------------------------------------------------------------
# Query builders shared by the top-level queries and the nested fields.
# Each one returns an unlimited SQLAlchemy query; the caller applies the limit.
# ---------------------------------------------------------------------------


def clinical_gene_rows(session, model, gene, sample_id, dataset_id):
    """Rows from clinical_rna / clinical_cnv / clinical_mutation."""
    query = session.query(model)
    if gene:
        query = query.filter(model.gene_id.in_(find_gene_ids(session, gene)))
    if sample_id:
        query = query.filter(model.sample_id == sample_id)
    return filter_by_clinical_dataset(query, model, dataset_id)


def pre_clinical_gene_rows(session, model, gene, sample_id, dataset_id):
    """Rows from pre_clinical_rna_seq / _microarray / _copy_number_variation."""
    query = session.query(model)
    if gene:
        query = query.filter(model.gene_id.in_(find_gene_ids(session, gene)))
    if sample_id:
        query = query.filter(model.sample_id == sample_id)
    return filter_by_pre_clinical_dataset(query, model, dataset_id)


def clinical_mutation_rows(session, gene, sample_id, dataset_id, mutated):
    query = clinical_gene_rows(session, ClinicalMutation, gene, sample_id, dataset_id)
    if mutated is not None:
        query = query.filter(ClinicalMutation.mutation == mutated)
    return query


def clinical_mirna_rows(session, mirna, sample_id, dataset_id):
    query = session.query(ClinicalMiRNA)
    if mirna:
        query = query.filter(ClinicalMiRNA.id.contains(mirna))
    if sample_id:
        query = query.filter(ClinicalMiRNA.sample_id == sample_id)
    return filter_by_clinical_dataset(query, ClinicalMiRNA, dataset_id)


def clinical_rppa_rows(session, antigen, gene, sample_id, dataset_id):
    query = session.query(ClinicalRPPA)
    if antigen or gene:
        # Find the antigens first, then the RPPA values for them
        antigen_query = session.query(ClinicalAntigen.id)
        if antigen:
            antigen_query = antigen_query.filter(
                or_(
                    ClinicalAntigen.id == antigen,
                    ClinicalAntigen.peptide_target.contains(antigen),
                )
            )
        if gene:
            antigen_query = antigen_query.filter(
                ClinicalAntigen.peptide_target_gene.in_(find_gene_ids(session, gene))
            )
        antigen_ids = [row.id for row in antigen_query.all()]
        query = query.filter(ClinicalRPPA.antigen_id.in_(antigen_ids))
    if sample_id:
        query = query.filter(ClinicalRPPA.sample_id == sample_id)
    return filter_by_clinical_dataset(query, ClinicalRPPA, dataset_id)


def clinical_methylation_rows(session, probe_id, gene, sample_id, dataset_id):
    query = session.query(ClinicalMethylation)
    if probe_id:
        query = query.filter(ClinicalMethylation.probe_id == probe_id)
    if gene:
        # clinical_probe.name holds the gene symbol the probe sits in
        probe_ids = [
            row.id
            for row in session.query(ClinicalProbe.id)
            .filter(ClinicalProbe.name == gene)
            .all()
        ]
        query = query.filter(ClinicalMethylation.probe_id.in_(probe_ids))
    if sample_id:
        query = query.filter(ClinicalMethylation.sample_id == sample_id)
    return filter_by_clinical_dataset(query, ClinicalMethylation, dataset_id)


def treatment_response_rows(session, dataset_id, cell_line_name, treatment_id, cid):
    query = session.query(PreClinicalTreatmentResponse)
    if dataset_id is not None:
        query = query.filter(PreClinicalTreatmentResponse.dataset_id == dataset_id)
    if cell_line_name:
        query = query.filter(
            PreClinicalTreatmentResponse.cell_line_name.contains(cell_line_name)
        )
    if treatment_id:
        query = query.filter(
            PreClinicalTreatmentResponse.treatment_id.contains(treatment_id)
        )
    if cid:
        query = query.filter(PreClinicalTreatmentResponse.cid == cid)
    return query


def find_cell_line(session, cell_line_name: str, dataset_id: int):
    """Cell lines are linked by (cell_line_name, dataset_id), not by id."""
    return (
        session.query(PreClinicalCellLine)
        .filter(
            PreClinicalCellLine.cell_line_name == cell_line_name,
            PreClinicalCellLine.dataset_id == dataset_id,
        )
        .first()
    )


# ---------------------------------------------------------------------------
# Shared types: datasets, genes and drugs.
# Strawberry reads each field straight off the SQLAlchemy row, so inside a
# resolver "self" is that row (e.g. a Dataset object).
# ---------------------------------------------------------------------------


@strawberry.type(
    description="A gene (Ensembl id and gene symbol). Used by clinical and pre-clinical data."
)
class GeneType:
    id: str
    name: str | None


@strawberry.type(description="A clinical or pre-clinical dataset.")
class DatasetType:
    id: int
    name: str
    version: str | None
    software: str | None
    link: str | None
    publication: str | None
    description: str | None
    key_study_findings: str | None
    clinical: bool | None

    @strawberry.field(description="PubMed id of the publication.")
    def pmid(self) -> str | None:
        # The database column is upper case ("PMID")
        return self.PMID

    @strawberry.field(
        description="Data types this dataset actually has data for, e.g. 'RNA-seq', 'Mutation', 'Treatment Response'."
    )
    def data_layers(self, info: Info) -> list[str]:
        return find_available_data_layers(self.id, self.clinical, get_session(info))

    @strawberry.field(description="Patient samples (clinical datasets only).")
    def clinical_samples(
        self, info: Info, limit: int = 50
    ) -> list["ClinicalSampleType"]:
        query = (
            get_session(info)
            .query(ClinicalSample)
            .filter(ClinicalSample.dataset_id == self.id)
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(description="Whole slide images (clinical datasets only).")
    def slides(self, info: Info, limit: int = 50) -> list["ClinicalSlideType"]:
        query = (
            get_session(info)
            .query(ClinicalSlide)
            .filter(ClinicalSlide.dataset_id == self.id)
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(description="Cell lines (pre-clinical datasets only).")
    def cell_lines(self, info: Info, limit: int = 50) -> list["CellLineType"]:
        query = (
            get_session(info)
            .query(PreClinicalCellLine)
            .filter(PreClinicalCellLine.dataset_id == self.id)
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(description="Cell line samples (pre-clinical datasets only).")
    def pre_clinical_samples(
        self, info: Info, limit: int = 50
    ) -> list["PreClinicalSampleType"]:
        query = (
            get_session(info)
            .query(PreClinicalSample)
            .filter(PreClinicalSample.dataset_id == self.id)
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(description="Drug responses (pre-clinical datasets only).")
    def treatment_responses(
        self, info: Info, limit: int = 50
    ) -> list["TreatmentResponseType"]:
        query = (
            get_session(info)
            .query(PreClinicalTreatmentResponse)
            .filter(PreClinicalTreatmentResponse.dataset_id == self.id)
        )
        return query.limit(clamp_limit(limit)).all()


@strawberry.type(description="A drug/compound, keyed by PubChem CID.")
class DrugType:
    cid: str
    title: str | None
    mapped_name: str | None
    molecule_chembl_id: str | None
    molecular_formula: str | None
    molecular_weight: str | None
    smiles: str | None
    iupac_name: str | None
    chembl_max_phase: int | None
    drug_like: bool | None
    fda_approval: bool | None
    atc_code: str | None
    mechanism_action_type: str | None
    mechanism_of_action: str | None

    @strawberry.field(description="Cell line responses to this drug (matched on cid).")
    def treatment_responses(
        self, info: Info, limit: int = 50
    ) -> list["TreatmentResponseType"]:
        query = (
            get_session(info)
            .query(PreClinicalTreatmentResponse)
            .filter(PreClinicalTreatmentResponse.cid == self.cid)
        )
        return query.limit(clamp_limit(limit)).all()


# ---------------------------------------------------------------------------
# Clinical types (patients).
# ---------------------------------------------------------------------------


@strawberry.type(description="A patient sample from a clinical dataset.")
class ClinicalSampleType:
    id: str
    dataset_id: int
    race: str | None
    ethnicity: str | None
    sex: str | None
    age: int | None
    histology: str | None
    tissue: str | None
    tissue_origin: str | None

    @strawberry.field
    def dataset(self, info: Info) -> DatasetType | None:
        return get_session(info).get(Dataset, self.dataset_id)

    @strawberry.field(description="Whole slide images of this sample.")
    def slides(self, info: Info) -> list["ClinicalSlideType"]:
        return (
            get_session(info)
            .query(ClinicalSlide)
            .filter(ClinicalSlide.sample_id == self.id)
            .all()
        )

    @strawberry.field(
        description="RNA-seq expression (TPM). 'gene' is a symbol or Ensembl id."
    )
    def rna(
        self, info: Info, gene: str | None = None, limit: int = 50
    ) -> list["ClinicalRnaType"]:
        query = clinical_gene_rows(get_session(info), ClinicalRNA, gene, self.id, None)
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Copy number per gene. 'gene' is a symbol or Ensembl id."
    )
    def copy_number_variations(
        self, info: Info, gene: str | None = None, limit: int = 50
    ) -> list["ClinicalCnvType"]:
        query = clinical_gene_rows(get_session(info), ClinicalCNV, gene, self.id, None)
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Mutation status per gene. Set mutated=true to list only mutated genes."
    )
    def mutations(
        self,
        info: Info,
        gene: str | None = None,
        mutated: bool | None = None,
        limit: int = 50,
    ) -> list["ClinicalMutationType"]:
        query = clinical_mutation_rows(get_session(info), gene, self.id, None, mutated)
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="miRNA expression (RPM). 'mirna' matches the miRNA id, e.g. 'hsa-mir-21'."
    )
    def mirna(
        self, info: Info, mirna: str | None = None, limit: int = 50
    ) -> list["ClinicalMirnaType"]:
        query = clinical_mirna_rows(get_session(info), mirna, self.id, None)
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Protein expression (RPPA). 'antigen' matches the antigen id or peptide target."
    )
    def rppa(
        self,
        info: Info,
        antigen: str | None = None,
        gene: str | None = None,
        limit: int = 50,
    ) -> list["ClinicalRppaType"]:
        query = clinical_rppa_rows(get_session(info), antigen, gene, self.id, None)
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="DNA methylation (beta values). 'gene' matches the probe's gene symbol."
    )
    def methylation(
        self,
        info: Info,
        probe_id: str | None = None,
        gene: str | None = None,
        limit: int = 50,
    ) -> list["ClinicalMethylationType"]:
        query = clinical_methylation_rows(
            get_session(info), probe_id, gene, self.id, None
        )
        return query.limit(clamp_limit(limit)).all()


@strawberry.type(description="An RPPA antigen (protein target).")
class ClinicalAntigenType:
    id: str
    catalogue_number: str | None
    peptide_target: str | None
    peptide_target_gene: str | None

    @strawberry.field(description="The gene this antigen targets, if known.")
    def gene(self, info: Info) -> GeneType | None:
        if self.peptide_target_gene is None:
            return None
        return get_session(info).get(PreClinicalGene, self.peptide_target_gene)


@strawberry.type(
    description="A methylation array probe. 'name' is the gene symbol it sits in."
)
class ClinicalProbeType:
    id: str
    name: str | None


@strawberry.type(
    description="RNA-seq expression of one gene in one patient sample (TPM)."
)
class ClinicalRnaType:
    gene_id: str
    sample_id: str
    value: float | None

    @strawberry.field
    def gene(self, info: Info) -> GeneType | None:
        return get_session(info).get(PreClinicalGene, self.gene_id)

    @strawberry.field
    def sample(self, info: Info) -> ClinicalSampleType | None:
        return get_session(info).get(ClinicalSample, self.sample_id)


@strawberry.type(description="Copy number of one gene in one patient sample.")
class ClinicalCnvType:
    gene_id: str
    sample_id: str
    value: int | None

    @strawberry.field
    def gene(self, info: Info) -> GeneType | None:
        return get_session(info).get(PreClinicalGene, self.gene_id)

    @strawberry.field
    def sample(self, info: Info) -> ClinicalSampleType | None:
        return get_session(info).get(ClinicalSample, self.sample_id)


@strawberry.type(description="Whether one gene is mutated in one patient sample.")
class ClinicalMutationType:
    gene_id: str
    sample_id: str
    mutation: bool | None = strawberry.field(
        description="True if the gene is mutated in this sample."
    )
    oncoprint: str | None = strawberry.field(
        description="Mutation type, e.g. 'Missense_Mutation', 'Frame_Shift_Del'."
    )

    @strawberry.field
    def gene(self, info: Info) -> GeneType | None:
        return get_session(info).get(PreClinicalGene, self.gene_id)

    @strawberry.field
    def sample(self, info: Info) -> ClinicalSampleType | None:
        return get_session(info).get(ClinicalSample, self.sample_id)


@strawberry.type(description="Expression of one miRNA in one patient sample (RPM).")
class ClinicalMirnaType:
    id: str = strawberry.field(description="miRNA id, e.g. 'hsa-let-7a-1'.")
    sample_id: str
    value: float | None

    @strawberry.field
    def sample(self, info: Info) -> ClinicalSampleType | None:
        return get_session(info).get(ClinicalSample, self.sample_id)


@strawberry.type(
    description="Protein expression of one antigen in one patient sample (RPPA)."
)
class ClinicalRppaType:
    antigen_id: str
    sample_id: str
    value: float | None

    @strawberry.field
    def antigen(self, info: Info) -> ClinicalAntigenType | None:
        return get_session(info).get(ClinicalAntigen, self.antigen_id)

    @strawberry.field
    def sample(self, info: Info) -> ClinicalSampleType | None:
        return get_session(info).get(ClinicalSample, self.sample_id)


@strawberry.type(
    description="Methylation of one probe in one patient sample (beta value, 0 to 1)."
)
class ClinicalMethylationType:
    probe_id: str
    sample_id: str
    value: float | None

    @strawberry.field
    def probe(self, info: Info) -> ClinicalProbeType | None:
        return get_session(info).get(ClinicalProbe, self.probe_id)

    @strawberry.field
    def sample(self, info: Info) -> ClinicalSampleType | None:
        return get_session(info).get(ClinicalSample, self.sample_id)


@strawberry.type(
    description="A whole slide image (pathology). One sample can have several slides."
)
class ClinicalSlideType:
    id: str
    sample_id: str
    dataset_id: int
    n_tiles: int
    embedding_dim: int

    @strawberry.field
    def sample(self, info: Info) -> ClinicalSampleType | None:
        return get_session(info).get(ClinicalSample, self.sample_id)

    @strawberry.field
    def dataset(self, info: Info) -> DatasetType | None:
        return get_session(info).get(Dataset, self.dataset_id)

    @strawberry.field(description="Tiles cut from this slide.")
    def tiles(self, info: Info, limit: int = 50) -> list["ClinicalTileType"]:
        query = (
            get_session(info)
            .query(ClinicalTile)
            .filter(ClinicalTile.slide_id == self.id)
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Embeddings computed for this slide. kind is 'tile' or 'slide_mean'."
    )
    def embeddings(
        self, info: Info, kind: str | None = None, limit: int = 50
    ) -> list["ClinicalEmbeddingType"]:
        query = (
            get_session(info)
            .query(ClinicalEmbedding)
            .filter(ClinicalEmbedding.slide_id == self.id)
        )
        if kind:
            query = query.filter(ClinicalEmbedding.kind == kind)
        return query.limit(clamp_limit(limit)).all()


@strawberry.type(
    description="One tile of a whole slide image, with its position on the slide."
)
class ClinicalTileType:
    id: int
    slide_id: str
    tile_index: int
    x: float
    y: float

    @strawberry.field
    def slide(self, info: Info) -> ClinicalSlideType | None:
        return get_session(info).get(ClinicalSlide, self.slide_id)


@strawberry.type(
    description="Metadata for an image embedding of a slide or tile. The vector itself is not exposed."
)
class ClinicalEmbeddingType:
    id: int
    slide_id: str
    tile_id: int | None = strawberry.field(
        description="Empty for slide-level (kind='slide_mean') rows."
    )
    model_name: str
    kind: str

    @strawberry.field
    def slide(self, info: Info) -> ClinicalSlideType | None:
        return get_session(info).get(ClinicalSlide, self.slide_id)

    @strawberry.field
    def tile(self, info: Info) -> ClinicalTileType | None:
        if self.tile_id is None:
            return None
        return get_session(info).get(ClinicalTile, self.tile_id)


# ---------------------------------------------------------------------------
# Pre-clinical types (cell lines).
# ---------------------------------------------------------------------------


@strawberry.type(
    description="Extra Cellosaurus details for a cell line (matched on accession)."
)
class CellLineInfoType:
    accession: str
    cell_line_name: str | None
    category: str | None
    age_at_sampling: str | None
    sex_of_cell: str | None
    cell_type: str | None
    derived_from_site: str | None
    disease_ids: str | None
    disease_descriptions: str | None
    first_level: str | None = strawberry.field(
        description="OncoTree top level, e.g. 'SOFT TISSUE'."
    )
    second_level: str | None = strawberry.field(
        description="OncoTree tumor type, e.g. 'Leiomyosarcoma'."
    )
    doubling_time: str | None
    genome_ancestry: str | None
    hla_typing: str | None
    microsatellite_instability: str | None
    sequence_variation: str | None
    karyotypic_information: str | None
    omics: str | None
    problematic_cell_line: str | None
    caution: str | None


def find_cell_line_info(info: Info, accession: str | None):
    if accession is None:
        return None
    return get_session(info).get(PreClinicalCellLineInfo, accession)


@strawberry.type(description="A cell line from a pre-clinical dataset.")
class CellLineType:
    id: int
    dataset_id: int
    cell_line_name: str
    tissueid: str | None
    mod_tissueid: str | None
    accession: str | None
    category: str | None
    sex: str | None
    age: int | None

    # Shortcuts to the most useful fields of pre_clinical_cell_line_info
    @strawberry.field(
        description="Disease description(s), e.g. 'Vulvar leiomyosarcoma|Leiomyosarcoma'."
    )
    def disease(self, info: Info) -> str | None:
        cell_line_info = find_cell_line_info(info, self.accession)
        return cell_line_info.disease_descriptions if cell_line_info else None

    @strawberry.field(description="OncoTree top level, e.g. 'SOFT TISSUE'.")
    def oncotree_level_1(self, info: Info) -> str | None:
        cell_line_info = find_cell_line_info(info, self.accession)
        return cell_line_info.first_level if cell_line_info else None

    @strawberry.field(description="OncoTree tumor type, e.g. 'Leiomyosarcoma'.")
    def oncotree_level_2(self, info: Info) -> str | None:
        cell_line_info = find_cell_line_info(info, self.accession)
        return cell_line_info.second_level if cell_line_info else None

    @strawberry.field(description="All Cellosaurus details for this cell line.")
    def details(self, info: Info) -> CellLineInfoType | None:
        return find_cell_line_info(info, self.accession)

    @strawberry.field
    def dataset(self, info: Info) -> DatasetType | None:
        return get_session(info).get(Dataset, self.dataset_id)

    @strawberry.field(description="Molecular profiling samples of this cell line.")
    def samples(self, info: Info) -> list["PreClinicalSampleType"]:
        return (
            get_session(info)
            .query(PreClinicalSample)
            .filter(
                PreClinicalSample.cell_line_name == self.cell_line_name,
                PreClinicalSample.dataset_id == self.dataset_id,
            )
            .all()
        )

    @strawberry.field(
        description="Drug responses of this cell line. Cell lines have hundreds of "
        "responses, so pass 'treatmentId' (partial match, e.g. 'Doxorubicin') when "
        "looking for a specific drug."
    )
    def treatment_responses(
        self, info: Info, treatment_id: str | None = None, limit: int = 50
    ) -> list["TreatmentResponseType"]:
        query = (
            get_session(info)
            .query(PreClinicalTreatmentResponse)
            .filter(
                PreClinicalTreatmentResponse.cell_line_name == self.cell_line_name,
                PreClinicalTreatmentResponse.dataset_id == self.dataset_id,
            )
        )
        if treatment_id:
            query = query.filter(
                PreClinicalTreatmentResponse.treatment_id.contains(treatment_id)
            )
        return query.limit(clamp_limit(limit)).all()


@strawberry.type(
    description="A molecular profiling sample of a cell line (pre-clinical)."
)
class PreClinicalSampleType:
    id: str
    dataset_id: int
    cell_line_name: str

    @strawberry.field
    def dataset(self, info: Info) -> DatasetType | None:
        return get_session(info).get(Dataset, self.dataset_id)

    @strawberry.field
    def cell_line(self, info: Info) -> CellLineType | None:
        return find_cell_line(get_session(info), self.cell_line_name, self.dataset_id)

    @strawberry.field(
        description="RNA-seq expression. 'gene' is a symbol or Ensembl id."
    )
    def rna_seq(
        self, info: Info, gene: str | None = None, limit: int = 50
    ) -> list["PreClinicalRnaSeqType"]:
        query = pre_clinical_gene_rows(
            get_session(info), PreClinicalRnaSeq, gene, self.id, None
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Microarray expression. 'gene' is a symbol or Ensembl id."
    )
    def microarray(
        self, info: Info, gene: str | None = None, limit: int = 50
    ) -> list["PreClinicalMicroarrayType"]:
        query = pre_clinical_gene_rows(
            get_session(info), PreClinicalMicroarray, gene, self.id, None
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Copy number per gene. 'gene' is a symbol or Ensembl id."
    )
    def copy_number_variations(
        self, info: Info, gene: str | None = None, limit: int = 50
    ) -> list["PreClinicalCnvType"]:
        query = pre_clinical_gene_rows(
            get_session(info), PreClinicalCopyNumberVariation, gene, self.id, None
        )
        return query.limit(clamp_limit(limit)).all()


@strawberry.type(description="How a cell line responded to a drug (pre-clinical).")
class TreatmentResponseType:
    id: int
    dataset_id: int
    cell_line_name: str
    treatment_id: str
    cid: str | None = strawberry.field(description="PubChem CID of the drug.")
    ic50_recomputed: float | None = strawberry.field(
        description="IC50: the drug concentration that cuts cell "
        "viability in half. Lower means more sensitive. Recomputed with the PharmacoGx "
        "R package from the raw dose-response data, so values are comparable across datasets."
    )
    acc_recomputed: float | None = strawberry.field(
        description="Area above the dose-response curve (AAC)"
        "Recomputed with the PharmacoGx R package from the raw "
        "dose-response data, so values are comparable across datasets."
    )
    mechanism_of_action: str | None

    @strawberry.field
    def dataset(self, info: Info) -> DatasetType | None:
        return get_session(info).get(Dataset, self.dataset_id)

    @strawberry.field
    def cell_line(self, info: Info) -> CellLineType | None:
        return find_cell_line(get_session(info), self.cell_line_name, self.dataset_id)

    @strawberry.field(
        description="Drug details (matched on cid). Empty if the drug is not annotated."
    )
    def drug(self, info: Info) -> DrugType | None:
        if self.cid is None:
            return None
        return get_session(info).get(Drugs, self.cid)


@strawberry.type(description="RNA-seq expression of one gene in one cell line sample.")
class PreClinicalRnaSeqType:
    sample_id: str
    gene_id: str
    value: float

    @strawberry.field
    def gene(self, info: Info) -> GeneType | None:
        return get_session(info).get(PreClinicalGene, self.gene_id)

    @strawberry.field
    def sample(self, info: Info) -> PreClinicalSampleType | None:
        return get_session(info).get(PreClinicalSample, self.sample_id)


@strawberry.type(
    description="Microarray expression of one gene in one cell line sample."
)
class PreClinicalMicroarrayType:
    sample_id: str
    gene_id: str
    value: float

    @strawberry.field
    def gene(self, info: Info) -> GeneType | None:
        return get_session(info).get(PreClinicalGene, self.gene_id)

    @strawberry.field
    def sample(self, info: Info) -> PreClinicalSampleType | None:
        return get_session(info).get(PreClinicalSample, self.sample_id)


@strawberry.type(description="Copy number of one gene in one cell line sample.")
class PreClinicalCnvType:
    sample_id: str
    gene_id: str
    value: float

    @strawberry.field
    def gene(self, info: Info) -> GeneType | None:
        return get_session(info).get(PreClinicalGene, self.gene_id)

    @strawberry.field
    def sample(self, info: Info) -> PreClinicalSampleType | None:
        return get_session(info).get(PreClinicalSample, self.sample_id)


# ---------------------------------------------------------------------------
# Queries. Every filter is optional unless noted; text filters marked
# "matches" do a "contains" match, and 'gene' filters take an exact gene
# symbol (e.g. 'TP53') or Ensembl id.
# ---------------------------------------------------------------------------


@strawberry.type
class Query:
    # ---- Shared clinical and preclinical tables ----

    @strawberry.field(description="List datasets. Set clinical=true/false to filter.")
    def datasets(self, info: Info, clinical: bool | None = None) -> list[DatasetType]:
        query = get_session(info).query(Dataset)
        if clinical is not None:
            query = query.filter(Dataset.clinical == clinical)
        return query.all()

    @strawberry.field(description="List genes. 'name' matches the gene symbol.")
    def genes(
        self, info: Info, name: str | None = None, limit: int = 50
    ) -> list[GeneType]:
        query = get_session(info).query(PreClinicalGene)
        if name:
            query = query.filter(PreClinicalGene.name.contains(name))
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="List drugs. 'name' can be any drug name or synonym (e.g. "
        "'Doxorubicin', 'Adriamycin'); it is resolved through AnnotationDB and "
        "matched on PubChem CID, then on the drug title or treatmentId. The "
        "returned 'cid' is the one to use in treatmentResponses. 'cid' is an "
        "exact PubChem CID."
    )
    def drugs(
        self,
        info: Info,
        name: str | None = None,
        cid: str | None = None,
        fda_approval: bool | None = None,
        limit: int = 50,
    ) -> list[DrugType]:
        session = get_session(info)
        query = session.query(Drugs)
        if name:
            # Step 1: ask AnnotationDB which compounds this name refers to.
            annotationdb_matches = find_compounds_in_annotationdb(name)
            annotationdb_cids = [str(match["cid"]) for match in annotationdb_matches]

            # Step 2: if any of those CIDs are in the portal, search on them.
            cids_in_portal = [
                row.cid
                for row in session.query(Drugs.cid).filter(
                    Drugs.cid.in_(annotationdb_cids)
                )
            ]
            if cids_in_portal:
                query = query.filter(Drugs.cid.in_(cids_in_portal))
            else:
                # Step 3: no CID match. One name can map to several CIDs (e.g.
                # "Doxorubicin" is 31703 in AnnotationDB, but the portal's data
                # uses its salt, 32874), so search by name instead: the name
                # given plus the titles AnnotationDB returned for it.
                names_to_search = [name] + [
                    match["title"] for match in annotationdb_matches if match.get("title")
                ]
                name_conditions = []
                for name_to_search in names_to_search:
                    # Treatment names in the response data share the drug's cid.
                    cids_with_matching_treatment = session.query(
                        PreClinicalTreatmentResponse.cid
                    ).filter(
                        PreClinicalTreatmentResponse.treatment_id.contains(name_to_search)
                    )
                    name_conditions.append(Drugs.title.contains(name_to_search))
                    name_conditions.append(Drugs.cid.in_(cids_with_matching_treatment))
                query = query.filter(or_(*name_conditions))
        if cid:
            query = query.filter(Drugs.cid == cid)
        if fda_approval is not None:
            query = query.filter(Drugs.fda_approval == fda_approval)
        return query.limit(clamp_limit(limit)).all()

    # ---- Clinical ----

    @strawberry.field(description="List clinical (patient) samples.")
    def clinical_samples(
        self,
        info: Info,
        id: str | None = None,
        dataset_id: int | None = None,
        histology: str | None = None,
        tissue: str | None = None,
        sex: str | None = None,
        limit: int = 50,
    ) -> list[ClinicalSampleType]:
        query = get_session(info).query(ClinicalSample)
        if id:
            query = query.filter(ClinicalSample.id == id)
        if dataset_id is not None:
            query = query.filter(ClinicalSample.dataset_id == dataset_id)
        if histology:
            query = query.filter(ClinicalSample.histology.contains(histology))
        if tissue:
            query = query.filter(ClinicalSample.tissue.contains(tissue))
        if sex:
            query = query.filter(ClinicalSample.sex == sex)
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(description="Clinical RNA-seq (TPM). Requires gene or sampleId.")
    def clinical_rna(
        self,
        info: Info,
        gene: str | None = None,
        sample_id: str | None = None,
        dataset_id: int | None = None,
        limit: int = 50,
    ) -> list[ClinicalRnaType]:
        require_a_filter(gene=gene, sampleId=sample_id)
        query = clinical_gene_rows(
            get_session(info), ClinicalRNA, gene, sample_id, dataset_id
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(description="Clinical copy number. Requires gene or sampleId.")
    def clinical_copy_number_variations(
        self,
        info: Info,
        gene: str | None = None,
        sample_id: str | None = None,
        dataset_id: int | None = None,
        limit: int = 50,
    ) -> list[ClinicalCnvType]:
        require_a_filter(gene=gene, sampleId=sample_id)
        query = clinical_gene_rows(
            get_session(info), ClinicalCNV, gene, sample_id, dataset_id
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Clinical mutation status. Requires gene or sampleId. "
        "Set mutated=true to list only mutated rows, e.g. which samples have a TP53 mutation."
    )
    def clinical_mutations(
        self,
        info: Info,
        gene: str | None = None,
        sample_id: str | None = None,
        dataset_id: int | None = None,
        mutated: bool | None = None,
        limit: int = 50,
    ) -> list[ClinicalMutationType]:
        require_a_filter(gene=gene, sampleId=sample_id)
        query = clinical_mutation_rows(
            get_session(info), gene, sample_id, dataset_id, mutated
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Clinical miRNA (RPM). 'mirna' matches the miRNA id. Requires mirna or sampleId."
    )
    def clinical_mirna(
        self,
        info: Info,
        mirna: str | None = None,
        sample_id: str | None = None,
        dataset_id: int | None = None,
        limit: int = 50,
    ) -> list[ClinicalMirnaType]:
        require_a_filter(mirna=mirna, sampleId=sample_id)
        query = clinical_mirna_rows(get_session(info), mirna, sample_id, dataset_id)
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Clinical protein expression (RPPA). 'antigen' matches the antigen id or peptide target; "
        "'gene' matches the antigen's target gene. Requires antigen, gene or sampleId."
    )
    def clinical_rppa(
        self,
        info: Info,
        antigen: str | None = None,
        gene: str | None = None,
        sample_id: str | None = None,
        dataset_id: int | None = None,
        limit: int = 50,
    ) -> list[ClinicalRppaType]:
        require_a_filter(antigen=antigen, gene=gene, sampleId=sample_id)
        query = clinical_rppa_rows(
            get_session(info), antigen, gene, sample_id, dataset_id
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Clinical DNA methylation (beta values). 'gene' matches the probe's gene symbol. "
        "Requires probeId, gene or sampleId."
    )
    def clinical_methylation(
        self,
        info: Info,
        probe_id: str | None = None,
        gene: str | None = None,
        sample_id: str | None = None,
        dataset_id: int | None = None,
        limit: int = 50,
    ) -> list[ClinicalMethylationType]:
        require_a_filter(probeId=probe_id, gene=gene, sampleId=sample_id)
        query = clinical_methylation_rows(
            get_session(info), probe_id, gene, sample_id, dataset_id
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="List RPPA antigens. 'target' matches the peptide target."
    )
    def clinical_antigens(
        self, info: Info, target: str | None = None, limit: int = 50
    ) -> list[ClinicalAntigenType]:
        query = get_session(info).query(ClinicalAntigen)
        if target:
            query = query.filter(ClinicalAntigen.peptide_target.contains(target))
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="List methylation probes. 'gene' is the exact gene symbol."
    )
    def clinical_probes(
        self,
        info: Info,
        id: str | None = None,
        gene: str | None = None,
        limit: int = 50,
    ) -> list[ClinicalProbeType]:
        query = get_session(info).query(ClinicalProbe)
        if id:
            query = query.filter(ClinicalProbe.id == id)
        if gene:
            query = query.filter(ClinicalProbe.name == gene)
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="List whole slide images. Tiles and embeddings are nested fields."
    )
    def clinical_slides(
        self,
        info: Info,
        dataset_id: int | None = None,
        sample_id: str | None = None,
        limit: int = 50,
    ) -> list[ClinicalSlideType]:
        query = get_session(info).query(ClinicalSlide)
        if dataset_id is not None:
            query = query.filter(ClinicalSlide.dataset_id == dataset_id)
        if sample_id:
            query = query.filter(ClinicalSlide.sample_id == sample_id)
        return query.limit(clamp_limit(limit)).all()

    # ---- Pre-clinical ----

    @strawberry.field(
        description="List pre-clinical cell lines. 'tissue' matches mod_tissueid. "
        "'disease' matches the disease description or OncoTree levels, e.g. 'leiomyosarcoma'."
    )
    def cell_lines(
        self,
        info: Info,
        dataset_id: int | None = None,
        name: str | None = None,
        tissue: str | None = None,
        disease: str | None = None,
        limit: int = 50,
    ) -> list[CellLineType]:
        query = get_session(info).query(PreClinicalCellLine)
        if dataset_id is not None:
            query = query.filter(PreClinicalCellLine.dataset_id == dataset_id)
        if name:
            query = query.filter(PreClinicalCellLine.cell_line_name.contains(name))
        if tissue:
            query = query.filter(PreClinicalCellLine.mod_tissueid.contains(tissue))
        if disease:
            # The disease lives in pre_clinical_cell_line_info, matched on accession
            query = query.join(
                PreClinicalCellLineInfo,
                PreClinicalCellLine.accession == PreClinicalCellLineInfo.accession,
            ).filter(
                or_(
                    PreClinicalCellLineInfo.disease_descriptions.contains(disease),
                    PreClinicalCellLineInfo.first_level.contains(disease),
                    PreClinicalCellLineInfo.second_level.contains(disease),
                )
            )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="List cell line samples used for molecular profiling."
    )
    def pre_clinical_samples(
        self,
        info: Info,
        dataset_id: int | None = None,
        cell_line_name: str | None = None,
        limit: int = 50,
    ) -> list[PreClinicalSampleType]:
        query = get_session(info).query(PreClinicalSample)
        if dataset_id is not None:
            query = query.filter(PreClinicalSample.dataset_id == dataset_id)
        if cell_line_name:
            query = query.filter(
                PreClinicalSample.cell_line_name.contains(cell_line_name)
            )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="List drug responses of cell lines (IC50 / AAC). 'cid' is an exact PubChem CID."
    )
    def treatment_responses(
        self,
        info: Info,
        dataset_id: int | None = None,
        cell_line_name: str | None = None,
        treatment_id: str | None = None,
        cid: str | None = None,
        limit: int = 50,
    ) -> list[TreatmentResponseType]:
        query = treatment_response_rows(
            get_session(info), dataset_id, cell_line_name, treatment_id, cid
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(description="Pre-clinical RNA-seq. Requires gene or sampleId.")
    def pre_clinical_rna_seq(
        self,
        info: Info,
        gene: str | None = None,
        sample_id: str | None = None,
        dataset_id: int | None = None,
        limit: int = 50,
    ) -> list[PreClinicalRnaSeqType]:
        require_a_filter(gene=gene, sampleId=sample_id)
        query = pre_clinical_gene_rows(
            get_session(info), PreClinicalRnaSeq, gene, sample_id, dataset_id
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Pre-clinical microarray expression. Requires gene or sampleId."
    )
    def pre_clinical_microarray(
        self,
        info: Info,
        gene: str | None = None,
        sample_id: str | None = None,
        dataset_id: int | None = None,
        limit: int = 50,
    ) -> list[PreClinicalMicroarrayType]:
        require_a_filter(gene=gene, sampleId=sample_id)
        query = pre_clinical_gene_rows(
            get_session(info), PreClinicalMicroarray, gene, sample_id, dataset_id
        )
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(
        description="Pre-clinical copy number. Requires gene or sampleId."
    )
    def pre_clinical_copy_number_variations(
        self,
        info: Info,
        gene: str | None = None,
        sample_id: str | None = None,
        dataset_id: int | None = None,
        limit: int = 50,
    ) -> list[PreClinicalCnvType]:
        require_a_filter(gene=gene, sampleId=sample_id)
        query = pre_clinical_gene_rows(
            get_session(info),
            PreClinicalCopyNumberVariation,
            gene,
            sample_id,
            dataset_id,
        )
        return query.limit(clamp_limit(limit)).all()


schema = strawberry.Schema(query=Query)


# Give each GraphQL request its own database session.
def get_graphql_context(session=Depends(get_db_session)):
    return {"session": session}


router = GraphQLRouter(
    schema, context_getter=get_graphql_context, prefix="/graphql", tags=["GraphQL"]
)
