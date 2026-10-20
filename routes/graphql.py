"""
A small, read-only GraphQL schema over the portal's database.

It is used in two places:
  1. Mounted at /api/graphql so people can explore it in the browser (GraphiQL).
  2. By the AI assistant (routes/assistant.py), which writes GraphQL queries
     against this schema to answer user questions.

There are no mutations, so nothing here can change the database.
"""

import strawberry
from fastapi import Depends
from sqlalchemy import or_
from strawberry.fastapi import GraphQLRouter
from strawberry.types import Info

from database_session import get_db_session
from routes.dataset import find_available_data_layers
from models.tables import (
    Dataset,
    ClinicalSample,
    PreClinicalCellLine,
    PreClinicalCellLineInfo,
    PreClinicalTreatmentResponse,
    PreClinicalDrug,
    PreClinicalGene,
)

# Never return more than this many rows from a single query field.
MAX_ROWS = 500


def clamp_limit(limit: int) -> int:
    """Keep the requested row limit between 1 and MAX_ROWS."""
    return max(1, min(limit, MAX_ROWS))


# ---------------------------------------------------------------------------
# GraphQL types. Each one mirrors (a subset of) a SQLAlchemy model.
# Strawberry reads the matching attributes straight off the model objects.
# ---------------------------------------------------------------------------


@strawberry.type(description="A clinical or pre-clinical dataset.")
class DatasetType:
    id: int
    name: str
    version: str | None
    publication: str | None
    description: str | None
    key_study_findings: str | None
    clinical: bool | None

    @strawberry.field(
        description="Data types this dataset actually has data for, e.g. 'RNA-seq', 'Mutation', 'Treatment Response'."
    )
    def data_layers(self, info: Info) -> list[str]:
        # "self" here is the SQLAlchemy Dataset row
        session = info.context["session"]
        return find_available_data_layers(self.id, self.clinical, session)


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
    # The fields below come from pre_clinical_cell_line_info (matched on accession)
    disease: str | None = strawberry.field(
        description="Disease description(s), e.g. 'Vulvar leiomyosarcoma|Leiomyosarcoma'."
    )
    oncotree_level_1: str | None = strawberry.field(
        description="OncoTree top level, e.g. 'SOFT TISSUE'."
    )
    oncotree_level_2: str | None = strawberry.field(
        description="OncoTree tumor type, e.g. 'Leiomyosarcoma'."
    )


@strawberry.type(description="How a cell line responded to a drug (pre-clinical).")
class TreatmentResponseType:
    id: int
    dataset_id: int
    cell_line_name: str
    treatment_id: str
    cid: str | None
    ic50_recomputed: float | None
    acc_recomputed: float | None
    mechanism_of_action: str | None


@strawberry.type(description="A drug/compound, keyed by PubChem CID.")
class DrugType:
    cid: str
    title: str | None
    mapped_name: str | None
    molecule_chembl_id: str | None
    molecular_formula: str | None
    molecular_weight: str | None
    chembl_max_phase: int | None
    fda_approval: bool | None
    atc_code: str | None
    mechanism_action_type: str | None
    mechanism_of_action: str | None


@strawberry.type(description="A gene (Ensembl id and gene symbol).")
class GeneType:
    id: str
    name: str | None


# ---------------------------------------------------------------------------
# Queries. Every filter is optional; text filters do a "contains" match.
# The database session is passed in through the GraphQL context.
# ---------------------------------------------------------------------------


@strawberry.type
class Query:
    @strawberry.field(description="List datasets. Set clinical=true/false to filter.")
    def datasets(self, info: Info, clinical: bool | None = None) -> list[DatasetType]:
        session = info.context["session"]
        query = session.query(Dataset)
        if clinical is not None:
            query = query.filter(Dataset.clinical == clinical)
        return query.all()

    @strawberry.field(description="List clinical (patient) samples.")
    def clinical_samples(
        self,
        info: Info,
        dataset_id: int | None = None,
        histology: str | None = None,
        tissue: str | None = None,
        sex: str | None = None,
        limit: int = 50,
    ) -> list[ClinicalSampleType]:
        session = info.context["session"]
        query = session.query(ClinicalSample)
        if dataset_id is not None:
            query = query.filter(ClinicalSample.dataset_id == dataset_id)
        if histology:
            query = query.filter(ClinicalSample.histology.contains(histology))
        if tissue:
            query = query.filter(ClinicalSample.tissue.contains(tissue))
        if sex:
            query = query.filter(ClinicalSample.sex == sex)
        return query.limit(clamp_limit(limit)).all()

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
        session = info.context["session"]

        # Join each cell line to its info row (if any) so we can return its disease.
        query = session.query(PreClinicalCellLine, PreClinicalCellLineInfo).outerjoin(
            PreClinicalCellLineInfo,
            PreClinicalCellLine.accession == PreClinicalCellLineInfo.accession,
        )
        if dataset_id is not None:
            query = query.filter(PreClinicalCellLine.dataset_id == dataset_id)
        if name:
            query = query.filter(PreClinicalCellLine.cell_line_name.contains(name))
        if tissue:
            query = query.filter(PreClinicalCellLine.mod_tissueid.contains(tissue))
        if disease:
            query = query.filter(
                or_(
                    PreClinicalCellLineInfo.disease_descriptions.contains(disease),
                    PreClinicalCellLineInfo.first_level.contains(disease),
                    PreClinicalCellLineInfo.second_level.contains(disease),
                )
            )

        cell_lines = []
        for cell_line, cell_line_info in query.limit(clamp_limit(limit)).all():
            # cell_line_info is None when the cell line has no info row
            has_info = cell_line_info is not None
            cell_lines.append(
                CellLineType(
                    id=cell_line.id,
                    dataset_id=cell_line.dataset_id,
                    cell_line_name=cell_line.cell_line_name,
                    tissueid=cell_line.tissueid,
                    mod_tissueid=cell_line.mod_tissueid,
                    accession=cell_line.accession,
                    category=cell_line.category,
                    sex=cell_line.sex,
                    age=cell_line.age,
                    disease=cell_line_info.disease_descriptions if has_info else None,
                    oncotree_level_1=cell_line_info.first_level if has_info else None,
                    oncotree_level_2=cell_line_info.second_level if has_info else None,
                )
            )
        return cell_lines

    @strawberry.field(description="List drug responses of cell lines (IC50 / AAC).")
    def treatment_responses(
        self,
        info: Info,
        dataset_id: int | None = None,
        cell_line_name: str | None = None,
        treatment_id: str | None = None,
        limit: int = 50,
    ) -> list[TreatmentResponseType]:
        session = info.context["session"]
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
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(description="List drugs. 'name' matches the drug title.")
    def drugs(
        self, info: Info, name: str | None = None, limit: int = 50
    ) -> list[DrugType]:
        session = info.context["session"]
        query = session.query(PreClinicalDrug)
        if name:
            query = query.filter(PreClinicalDrug.title.contains(name))
        return query.limit(clamp_limit(limit)).all()

    @strawberry.field(description="List genes. 'name' matches the gene symbol.")
    def genes(
        self, info: Info, name: str | None = None, limit: int = 50
    ) -> list[GeneType]:
        session = info.context["session"]
        query = session.query(PreClinicalGene)
        if name:
            query = query.filter(PreClinicalGene.name.contains(name))
        return query.limit(clamp_limit(limit)).all()


schema = strawberry.Schema(query=Query)


# Give each GraphQL request its own database session.
def get_graphql_context(session=Depends(get_db_session)):
    return {"session": session}


router = GraphQLRouter(
    schema, context_getter=get_graphql_context, prefix="/graphql", tags=["GraphQL"]
)
