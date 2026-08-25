from collections import defaultdict
import os
from pydantic import BaseModel, Field
from typing import List
from urllib.parse import quote_plus
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import create_engine, select, or_, and_
import pandas as pd
from database_session import get_db_session
from models.tables import (
    PreClinicalSample,
    PreClinicalRnaSeq,
    PreClinicalCellLine,
    PreClinicalGene,
    PreClinicalTreatmentResponse,
)
from models.data_layers import pre_clinical_molecular_layers, pre_clinical_data_layers

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
        try:
            rows = (
                session.query(
                    PreClinicalGene.name.label("gene_name"),
                    PreClinicalSample.cell_line_name.label("cell_line"),
                    PreClinicalCellLine.tissueid.label("tissue"),
                    data_layer_model.value,
                )
                .join(PreClinicalSample, data_layer_model.sample_id == PreClinicalSample.id)
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
            print(f"Error querying molecular profile for {molecular_profile} (dataset_id={dataset_id}): {e}")
            raise HTTPException(
                status_code=404, detail=f"Molecular profile '{molecular_profile}' error: {e}"
            )
        
    else: 
        raise HTTPException(
            status_code=404, detail="Molecular profile not found for this dataset"
        )

    return result


@router.get(
    "/treatment-response",
    summary="Extract treatment response data for the given set of drug(s) for a specific dataset",
)
async def get_treatment_response(
    dataset_id: int = Query(
        description="Single dataset to pull treatment response data from",
        example=1,
    ),
    drug: List[str] = Query(
        default=None,
        description="The drug(s) you want data for",
        example=["(-)-Parthenolide"],
    ),
    # cell_lines: List[str] = Query(
    #     default=None,
    #     description="Optional list of cell lines to filter by",
    #     example=["A-204"],
    # ),
    session=Depends(get_db_session),
):
    if not dataset_id:
        raise HTTPException(
            status_code=400, detail="Need to include a dataset to get output"
        )
    elif not drug:
        raise HTTPException(
            status_code=400, detail="Need to include a drug to get output"
        )

    result = defaultdict(list)
    try:
        query = (
            session.query(
                PreClinicalTreatmentResponse.treatment_id.label("drug_name"),
                PreClinicalTreatmentResponse.cell_line_name.label("cell_line"),
                PreClinicalCellLine.tissueid.label("tissue"),
                PreClinicalTreatmentResponse.cid,
                PreClinicalTreatmentResponse.ic50_recomputed,
                PreClinicalTreatmentResponse.acc_recomputed,
            )
            .join(
                PreClinicalCellLine,
                and_(
                    PreClinicalTreatmentResponse.cell_line_name == PreClinicalCellLine.cell_line_name,
                    PreClinicalTreatmentResponse.dataset_id == PreClinicalCellLine.dataset_id,
                ),
            )
            .filter(PreClinicalTreatmentResponse.dataset_id == dataset_id)
        )

        if drug:
            drug_list = [d.strip() for item in drug for d in item.split(",") if d.strip()]
            if drug_list:
                query = query.filter(PreClinicalTreatmentResponse.treatment_id.in_(drug_list))

        # if cell_lines:
        #     cell_line_list = [c.strip() for item in cell_lines for c in item.split(",") if c.strip()]
        #     if cell_line_list:
        #         query = query.filter(PreClinicalTreatmentResponse.cell_line_name.in_(cell_line_list))

        rows = query.all()
        for drug_name, cell_line, tissue, cid, ic50_recomputed, acc_recomputed in rows:
            result[drug_name].append({
                "cellLine": cell_line,
                "ic50_recomputed": ic50_recomputed,
                "aac_recomputed": acc_recomputed,
                "tissue": tissue,
                "cid": cid,
            })
    except Exception as e:
        print(f"Error querying treatment response (dataset_id={dataset_id}): {e}")
        raise HTTPException(
            status_code=404, detail=f"Treatment response error: {e}"
        )

    return result
