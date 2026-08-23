from sqlalchemy import column
from models.pre_clinical_tables import PreClinicalTreatmentResponse
import os
from pydantic import BaseModel, Field
from typing import List
from urllib.parse import quote_plus
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import create_engine, select, or_
import pandas as pd
from database_session import get_db_session
from models.pre_clinical_tables import Datasets, PreClinicalSample, PreClinicalRnaSeq, PreClinicalMutation, PreClinicalMicroarray, PreClinicalCopyNumberVariation, PreClinicalTreatmentResponse, PreClinicalGene
from models.data_layers import pre_clinical_molecular_layers

router = APIRouter(prefix="/datasets", tags=["Datasets"])

pre_clinical_molecular_layers = {
    "RNA-seq": PreClinicalRnaSeq,
    "Copy Number Variation": PreClinicalCopyNumberVariation,
    "Microarray": PreClinicalMicroarray,    
}
    
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

# Get a single clinical or preclinical dataset statistics
@router.get(
    "/one/statistics",
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
        # get the data layers available for the dataset by mapping sample_ids to layers
        for data_layer_name, data_layer_model in pre_clinical_molecular_layers.items():
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
            session.query(pre_clinical_molecular_layers[molecular_profile].gene_id)
            .join(PreClinicalSample, pre_clinical_molecular_layers[molecular_profile].sample_id == PreClinicalSample.id)
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

def get_clinical_status (dataset_id, session = Depends(get_db_session)):

    try: 
        # deduce if dataset is clinical or pre clinical
        clinical = session.query(Datasets.clinical).filter(Datasets.id == dataset_id).scalar()

    except Exception as e:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return clinical


