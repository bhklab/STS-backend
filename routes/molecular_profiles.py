import os
from pydantic import BaseModel, Field
from typing import List
from urllib.parse import quote_plus
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import create_engine, select, or_
import pandas as pd
from database_session import get_db_session
from models.pre_clinical_tables import PreClinicalSample, PreClinicalRnaSeq

router = APIRouter(prefix="/molecular-profiles")

@router.get(
    "/rna-seq",
    summary="Extract cell line data by via cell line name",
)
async def get_rna_seq(
    dataset: str = Query(
        description="Single dataset to pull rna sequencing data from",
        example="CCLE,GDSC,L1000"
    ),
    session=Depends(get_db_session),
):
    if not dataset:
        raise HTTPException(
            status_code=400, detail="Need to include a dataset to get output"
        )

    session.query(PreClinicalRnaSeq, PreClinicalSample).join(PreClinicalSample, PreClinicalRnaSeq.sample_id == PreClinicalSample.sample_id).filter("dataset == "+dataset)
    

    return
