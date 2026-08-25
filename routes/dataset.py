from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import func, distinct
import pandas as pd
from database_session import get_db_session
from models.tables import (
    Datasets,
    PreClinicalSample,
    PreClinicalTreatmentResponse,
    PreClinicalGene,
)
from models.data_layers import pre_clinical_data_layers, pre_clinical_molecular_layers

router = APIRouter(prefix="/datasets", tags=["Datasets"])

    
# Get all clinical and preclinical datasets
@router.get(
    "/all",
    summary="Get all clinical and preclinical datasets",
)
async def get_all_datasets(
    session=Depends(get_db_session),
):
    rows = session.query(Datasets).all()
    return rows

# Get a single clinical or preclinical dataset
@router.get(
    "/one",
    summary="Get a single clinical or preclinical dataset",
)
async def get_single_dataset(
    dataset_id: str = Query(
        description="The id of the dataset we want to retrieve metadata for",
        example="1"
    ),
    session=Depends(get_db_session),
):
    dataset = session.query(Datasets).filter(Datasets.id == dataset_id).first()
    return dataset


# Get clinical or preclinical dataset statistics for dataset page
@router.get(
    "/statistics/dataset-page",
    summary="Get statistics for all clinical and preclinical datasets for dataset page",
)
async def get_all_dataset_statistics(
    session=Depends(get_db_session),
):
    datasets = session.query(Datasets).all()
    preclinical_datasets = []
    clinical_datasets = []

    for d in datasets:
        if d.clinical:
            clinical_datasets.append({
                "id": d.id,
                "name": d.name,
                "description": d.description,
                "version": d.version,
                "link": d.link,
                "publication": d.publication,
                "PMID": d.PMID,
                "key_study_findings": d.key_study_findings,
                "total_samples": 0,
                "total_genes": 0,
                "total_drugs": 0,
                "total_cell_lines": 0,
                "data_layers": []
            })
        else:
            samples = (
                session.query(func.count(distinct(PreClinicalSample.id)))
                .filter(PreClinicalSample.dataset_id == d.id)
                .scalar()
                or 0
            )
            total_cell_lines = (
                session.query(func.count(distinct(PreClinicalSample.cell_line_name)))
                .filter(PreClinicalSample.dataset_id == d.id)
                .scalar()
                or 0
            )
            total_drugs = (
                session.query(func.count(distinct(PreClinicalTreatmentResponse.treatment_id)))
                .filter(PreClinicalTreatmentResponse.dataset_id == d.id)
                .scalar()
                or 0
            )

            # Available data layers for this dataset
            available_layers = []
            for data_layer_name, data_layer_model in pre_clinical_data_layers.items():
                if data_layer_name == "Treatment Response":
                    has_layer = (
                        session.query(data_layer_model.id)
                        .filter(data_layer_model.dataset_id == d.id)
                        .first()
                        is not None
                    )
                else:
                    has_layer = (
                        session.query(data_layer_model.id)
                        .join(PreClinicalSample, data_layer_model.sample_id == PreClinicalSample.id)
                        .filter(PreClinicalSample.dataset_id == d.id)
                        .first()
                        is not None
                    )
                if has_layer:
                    available_layers.append(data_layer_name)

            # Total distinct genes across available molecular data layers
            gene_queries = [
                session.query(model.gene_id)
                .join(PreClinicalSample, model.sample_id == PreClinicalSample.id)
                .filter(PreClinicalSample.dataset_id == d.id)
                for name, model in pre_clinical_molecular_layers.items()
                if name in available_layers
            ]
            if gene_queries:
                combined_genes = (
                    gene_queries[0].union(*gene_queries[1:])
                    if len(gene_queries) > 1
                    else gene_queries[0]
                )
                total_genes = combined_genes.distinct().count()
            else:
                total_genes = 0

            preclinical_datasets.append({
                "id": d.id,
                "name": d.name,
                "description": d.description,
                "version": d.version,
                "link": d.link,
                "publication": d.publication,
                "PMID": d.PMID,
                "key_study_findings": d.key_study_findings,
                "total_samples": samples,
                "total_genes": total_genes,
                "total_drugs": total_drugs,
                "total_cell_lines": total_cell_lines,
                "data_layers": available_layers
            })

    return {
        "preclinical_datasets": preclinical_datasets,
        "clinical_datasets": clinical_datasets,
    }

# Get clinical or preclinical dataset statistics for landing page
@router.get(
    "/statistics/landing-page",
    summary="Get statistics for all clinical and preclinical datasets for landing page",
)
async def get_landing_page_dataset_statistics(
    session=Depends(get_db_session),
):
    total_pre_clinical_datasets = session.query(Datasets).filter(Datasets.clinical == False).count()
    total_clinical_datasets = session.query(Datasets).filter(Datasets.clinical == True).count()
    total_pre_clinical_samples = session.query(PreClinicalSample.id).distinct().count()
    total_drugs = session.query(PreClinicalTreatmentResponse.treatment_id).distinct().count()
    total_cell_lines = session.query(PreClinicalSample.cell_line_name).distinct().count()
    total_genes = session.query(PreClinicalGene.id).distinct().count()

    return {
        "total_clinical_datasets": total_clinical_datasets,
        "total_pre_clinical_datasets": total_pre_clinical_datasets,
        "total_pre_clinical_samples": total_pre_clinical_samples,
        "total_clinical_samples": 0,
        "total_drugs": total_drugs,
        "total_cell_lines": total_cell_lines,
        "total_genes": total_genes
    }

# Get a single clinical or preclinical dataset statistics
@router.get(
    "/statistics/one",
    summary="Get a single clinical or preclinical dataset",
)
async def get_single_dataset_statistics(
    dataset_id: int = Query(
        description="The id of the dataset we want to retrieve metadata for",
        example=1
    ),
    session=Depends(get_db_session),
):
    dataset = session.query(Datasets).filter(Datasets.id == dataset_id).first()
    return dataset


# Get all data layers the dataset has data for
@router.get(
    "/data-layers",
    summary="Get all data layers available for a given clinical or preclinical dataset",
)
async def get_all_data_layers(
    dataset_id: int = Query(
        description="The dataset for which we want to get data layers for.",
        example=1
    ),
    session=Depends(get_db_session),
):
    available_layers = []

    if get_clinical_status(dataset_id, session):
        return []
    else:
        # get the data layers available for the dataset by mapping sample ids to layers
        for data_layer_name, data_layer_model in pre_clinical_data_layers.items():
            if data_layer_name == "Treatment Response":
                row = (
                    session.query(data_layer_model.id)
                    .filter(data_layer_model.dataset_id == dataset_id)
                    .first()
                )
                if row:
                    available_layers.append(data_layer_name)
            else:
                row = (
                    session.query(data_layer_model.id)
                    .join(PreClinicalSample, data_layer_model.sample_id == PreClinicalSample.id)
                    .filter(PreClinicalSample.dataset_id == dataset_id)
                    .first()
                )
                if row:
                    available_layers.append(data_layer_name)

    return available_layers


# Get all genes from a given clinical or preclinical dataset + data layer
@router.get(
    "/genes",
    summary="Get all genes from a given clinical or preclinical dataset",
)
async def get_all_genes(
    dataset_id: int = Query(
        description="The id of the dataset we want to retrieve genes for",
        example=1
    ),
    molecular_profile: str = Query(
        description="select all genes for the data layer",
        example="RNA-seq"
    ),
    session=Depends(get_db_session),
):

    if get_clinical_status(dataset_id, session):
        return
    else:
        gene_sub_query = (
            session.query(pre_clinical_data_layers[molecular_profile].gene_id)
            .join(PreClinicalSample, pre_clinical_data_layers[molecular_profile].sample_id == PreClinicalSample.id)
            .filter(PreClinicalSample.dataset_id == dataset_id)
            .distinct()
            .subquery()
        )
        rows = (
            session.query(gene_sub_query.c.gene_id, PreClinicalGene.name)
            .join(PreClinicalGene, PreClinicalGene.id == gene_sub_query.c.gene_id)
            .all()
        )

    rows = [{"gene_id": row[0], "name": row[1]} for row in rows]

    return rows

# Get all drugs from a given clinical or preclinical dataset (could return MOA in the future as well for a filtering option)
@router.get(
    "/drugs",
    summary="Get all drugs from a given clinical or preclinical dataset",
)
async def get_all_drugs(
    dataset_id: int = Query(
        description="The id of the dataset we want to retrieve drugs for",
        example=1
    ),
    session=Depends(get_db_session),
):

    if get_clinical_status(dataset_id, session):
        return
    else:
        rows = (
            session.query(PreClinicalTreatmentResponse.treatment_id, PreClinicalTreatmentResponse.cid)
            .filter(PreClinicalTreatmentResponse.dataset_id == dataset_id)
            .distinct(PreClinicalTreatmentResponse.treatment_id)
            .all()
        )

    rows = [{"treatment_id": row[0], "cid": row[1]} for row in rows]

    return rows

def get_clinical_status (dataset_id, session = Depends(get_db_session)):

    try: 
        # deduce if dataset is clinical or pre clinical
        clinical = session.query(Datasets.clinical).filter(Datasets.id == dataset_id).scalar()

    except Exception as e:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return clinical


