from collections import defaultdict
import os
from pydantic import BaseModel, Field
from typing import List
from urllib.parse import quote_plus
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import create_engine, select, or_, and_
import pandas as pd
from database_session import get_db_session
from models.pre_clinical_tables import PreClinicalSample, PreClinicalRnaSeq, PreClinicalCellLine, PreClinicalGene
from models.data_layers import pre_clinical_molecular_layers

router = APIRouter(prefix="/data-layer", tags=["Data Layer"])

@router.get(
    "/molecular-profile",
    summary="Extract wanted molecular profile data for the given set of gene(s) for a specific dataset",
)
async def get_molecular_profile(
    dataset_id: int = Query(
        description="Single dataset to pull molecular profile data from",
        example=1
    ),
    molecular_profile: str = Query(
        description="The molecular profile you want data for",
        example="RNA-seq"
    ),
    gene: List[str] = Query(
        description="The genes you want data for",
        example="ENSG00000000003,ENSG00000004534"
    ),
    session=Depends(get_db_session),
):
    if not dataset_id:
        raise HTTPException(
            status_code=400, detail="Need to include a dataset to get output"
        )
    elif not gene:
        raise HTTPException(
            status_code=400, detail="Need to include a gene to get output"
        )
    elif not molecular_profile:
        raise HTTPException(
            status_code=400, detail="Need to include a molecular profile to get output"
        )
    
    

    result = defaultdict(list)
    data_layer_model = pre_clinical_molecular_layers.get(molecular_profile)
    if data_layer_model:
        val_col = getattr(data_layer_model, "expression_value", getattr(data_layer_model, "value", None))
        try: 
            rows = (
                session.query(
                    PreClinicalGene.name.label("gene_name"),
                    PreClinicalSample.cell_line_name.label("cell_line"),
                    PreClinicalCellLine.tissueid.label("tissue"),
                    val_col.label("value"),
                )
                .join(PreClinicalSample, data_layer_model.sample_id == PreClinicalSample.sampleid)
                .join(
                    PreClinicalCellLine,
                    and_(
                        PreClinicalSample.cell_line_name == PreClinicalCellLine.cell_line_name,
                        PreClinicalSample.dataset_id == PreClinicalCellLine.dataset_id,
                    ),
                )
                .join(PreClinicalGene, PreClinicalGene.id == data_layer_model.gene_id)
                .filter(PreClinicalSample.dataset_id == dataset_id)
                .filter(data_layer_model.gene_id.in_(gene))
                .all()
            )
            for gene_name, cell_line, tissue, value in rows:
                result[gene_name].append({
                    "cellLine": cell_line,
                    "value": value,
                    "tissue": tissue,
                })
        except Exception as e:
            raise HTTPException(
                status_code=404, detail="Molecular profile not found for this dataset"
            )
        
    else: 
        raise HTTPException(
            status_code=404, detail="Molecular profile not found for this dataset"
        )

    return result


    

    return


@router.get(
    "/treatment-response",
    summary="Extract cell line data by via cell line name",
)
async def get_treatment_response(
    dataset: str = Query(
        description="Single dataset to pull rna sequencing data from",
        example="CCLE,GDSC,L1000"
    ),
    response_type: str = Query(
        description="The type of response data to extract (either AAC or ic50)",
        example="IC50"
    ),
    cell_lines: List[object] = Query(),
    session=Depends(get_db_session),
):
    if not dataset:
        raise HTTPException(
            status_code=400, detail="Need to include a dataset to get output"
        )

    
    return
