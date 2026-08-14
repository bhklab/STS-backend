import os
import strawberry
from strawberry.fastapi import GraphQLRouter
from fastapi import APIRouter HTTPException, Depends, Query
from database_session import get_db_session

router = APIRouter(prefix="/graphql", tags=["GraphQL"])

@strawberry.type
class Dataset:
	id: str
	name: str
	version: str
	description: str
	layers: str

@strawberry.type
class sample:
	id: str # sample_id
	patient_id: str
	age_at_index: int | None
	age_at_diagnosis: str | None
	diseast_type: str | None
	primary_site: str | None
	tumor_definition: str | None
	classification_tumour: str | None
	primary_diagnosis_l1: str | None
	primary_diagnosis_l2: str | None
	prior_malignancy: str | None

	

@router.get("/")

