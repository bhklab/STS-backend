from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import func, distinct, and_
import pandas as pd
from database_session import get_db_session
from models.tables import (
    Dataset,
    PreClinicalSample,
    PreClinicalTreatmentResponse,
    PreClinicalDrug,
    PreClinicalGene,
    PreClinicalRnaSeq,
    PreClinicalCopyNumberVariation,
    PreClinicalMicroarray,
    ClinicalSample,
    ClinicalAntigen,
    ClinicalProbe,
    ClinicalMiRNA,
    ClinicalRNA,
    ClinicalCNV,
    ClinicalMutation,
    ClinicalRPPA,
    ClinicalMethylation,
    ClinicalSlide,
)
from models.data_layers import (
    pre_clinical_data_layers,
    pre_clinical_molecular_layers,
    clinical_data_layers,
    clinical_molecular_layers,
)

router = APIRouter(prefix="/datasets", tags=["Datasets"])

    
# Get all clinical and preclinical datasets
@router.get(
    "/all",
    summary="Get all clinical and preclinical datasets",
)
async def get_all_datasets(
    session=Depends(get_db_session),
):
    rows = session.query(Dataset).all()
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
    dataset = session.query(Dataset).filter(Dataset.id == dataset_id).first()
    return dataset


# Get clinical or preclinical dataset statistics for dataset page
@router.get(
    "/statistics/dataset-page",
    summary="Get statistics for all clinical and preclinical datasets for dataset page",
)
async def get_all_dataset_statistics(
    session=Depends(get_db_session),
):
    datasets = session.query(Dataset).all()

    # Pre-calculate sample and cell-line counts in single batch queries
    pc_samples = dict(
        session.query(PreClinicalSample.dataset_id, func.count(PreClinicalSample.id))
        .group_by(PreClinicalSample.dataset_id)
        .all()
    )
    pc_cell_lines = dict(
        session.query(PreClinicalSample.dataset_id, func.count(distinct(PreClinicalSample.cell_line_name)))
        .group_by(PreClinicalSample.dataset_id)
        .all()
    )
    cl_samples = dict(
        session.query(ClinicalSample.dataset_id, func.count(ClinicalSample.id))
        .group_by(ClinicalSample.dataset_id)
        .all()
    )

    # Pre-calculate drug counts per dataset
    pc_drugs = dict(
        session.query(PreClinicalTreatmentResponse.dataset_id, func.count(distinct(PreClinicalTreatmentResponse.treatment_id)))
        .group_by(PreClinicalTreatmentResponse.dataset_id)
        .all()
    )

    # Pre-calculate layer availability per dataset via distinct dataset_id lookups
    pc_layer_datasets = {
        "Treatment Response": set(r[0] for r in session.query(PreClinicalTreatmentResponse.dataset_id).distinct().all()),
        "RNA-seq": set(r[0] for r in session.query(PreClinicalSample.dataset_id).join(PreClinicalRnaSeq, PreClinicalRnaSeq.sample_id == PreClinicalSample.id).distinct().all()),
        "Copy Number Variation": set(r[0] for r in session.query(PreClinicalSample.dataset_id).join(PreClinicalCopyNumberVariation, PreClinicalCopyNumberVariation.sample_id == PreClinicalSample.id).distinct().all()),
        "Microarray": set(r[0] for r in session.query(PreClinicalSample.dataset_id).join(PreClinicalMicroarray, PreClinicalMicroarray.sample_id == PreClinicalSample.id).distinct().all()),
    }

    cl_layer_datasets = {
        "RNA-seq": set(r[0] for r in session.query(ClinicalSample.dataset_id).join(ClinicalRNA, ClinicalRNA.sample_id == ClinicalSample.id).distinct().all()),
        "Copy Number Variation": set(r[0] for r in session.query(ClinicalSample.dataset_id).join(ClinicalCNV, ClinicalCNV.sample_id == ClinicalSample.id).distinct().all()),
        "MiRNA": set(r[0] for r in session.query(ClinicalSample.dataset_id).join(ClinicalMiRNA, ClinicalMiRNA.sample_id == ClinicalSample.id).distinct().all()),
        "Mutation": set(r[0] for r in session.query(ClinicalSample.dataset_id).join(ClinicalMutation, ClinicalMutation.sample_id == ClinicalSample.id).distinct().all()),
        "RPPA": set(r[0] for r in session.query(ClinicalSample.dataset_id).join(ClinicalRPPA, ClinicalRPPA.sample_id == ClinicalSample.id).distinct().all()),
        "Methylation": set(r[0] for r in session.query(ClinicalSample.dataset_id).join(ClinicalMethylation, ClinicalMethylation.sample_id == ClinicalSample.id).distinct().all()),
        "Pathology": set(r[0] for r in session.query(ClinicalSlide.dataset_id).distinct().all()),
    }

    preclinical_datasets = []
    clinical_datasets = []

    for d in datasets:
        if d.clinical:
            avail_layers = [name for name, dsets in cl_layer_datasets.items() if d.id in dsets]
            # Calculate clinical total genes dynamically on the fly
            if "RNA-seq" in avail_layers:
                first_sample = session.query(ClinicalSample.id).filter(ClinicalSample.dataset_id == d.id).first()
                if first_sample:
                    total_genes = (
                        session.query(func.count(distinct(ClinicalRNA.gene_id)))
                        .filter(ClinicalRNA.sample_id == first_sample[0])
                        .filter(ClinicalRNA.gene_id.isnot(None))
                        .scalar()
                        or 0
                    )
                else:
                    total_genes = 0
            elif "Copy Number Variation" in avail_layers:
                first_sample = session.query(ClinicalSample.id).filter(ClinicalSample.dataset_id == d.id).first()
                if first_sample:
                    total_genes = (
                        session.query(func.count(distinct(ClinicalCNV.gene_id)))
                        .filter(ClinicalCNV.sample_id == first_sample[0])
                        .filter(ClinicalCNV.gene_id.isnot(None))
                        .scalar()
                        or 0
                    )
                else:
                    total_genes = 0
            elif "Mutation" in avail_layers:
                total_genes = (
                    session.query(func.count(distinct(ClinicalMutation.gene_id)))
                    .join(ClinicalSample, ClinicalMutation.sample_id == ClinicalSample.id)
                    .filter(ClinicalSample.dataset_id == d.id)
                    .filter(ClinicalMutation.gene_id.isnot(None))
                    .scalar()
                    or 0
                )
            else:
                total_genes = 0

            total_slides = 0
            total_tiles = 0
            if "Pathology" in avail_layers:
                total_slides = session.query(func.count(ClinicalSlide.id)).filter(ClinicalSlide.dataset_id == d.id).scalar() or 0
                total_tiles = session.query(func.sum(ClinicalSlide.n_tiles)).filter(ClinicalSlide.dataset_id == d.id).scalar() or 0
                emb_res = session.query(ClinicalSlide.embedding_dim).filter(ClinicalSlide.dataset_id == d.id).first()

            # Calculate histology and sex counts across all samples for this clinical dataset
            histology_counts = {}
            sex_counts = {}
            samples = session.query(ClinicalSample.histology, ClinicalSample.sex).filter(ClinicalSample.dataset_id == d.id).all()
            for s in samples:
                h = s.histology if s.histology else "Unknown"
                histology_counts[h] = histology_counts.get(h, 0) + 1

                sx = s.sex if s.sex else "Unknown"
                if sx == "M":
                    sx = "Male"
                elif sx == "F":
                    sx = "Female"
                sex_counts[sx] = sex_counts.get(sx, 0) + 1

            clinical_datasets.append({
                "id": d.id,
                "name": d.name,
                "description": d.description,
                "software": d.software,
                "version": d.version,
                "link": d.link,
                "publication": d.publication,
                "PMID": d.PMID,
                "key_study_findings": d.key_study_findings,
                "total_samples": cl_samples.get(d.id, 0),
                "total_genes": total_genes,
                "total_drugs": 0,
                "total_cell_lines": 0,
                "total_slides": total_slides,
                "total_tiles": total_tiles,
                "histology_counts": histology_counts,
                "sex_counts": sex_counts,
                "data_layers": avail_layers,
            })
        else:
            avail_layers = [name for name, dsets in pc_layer_datasets.items() if d.id in dsets]
            # Calculate pre-clinical total genes dynamically on the fly
            gene_queries = []
            sample_ids_subquery = session.query(PreClinicalSample.id).filter(PreClinicalSample.dataset_id == d.id).subquery()
            for name in avail_layers:
                if name in pre_clinical_molecular_layers:
                    model = pre_clinical_molecular_layers[name]
                    gene_queries.append(
                        session.query(model.gene_id)
                        .filter(model.sample_id.in_(session.query(sample_ids_subquery.c.id)))
                    )
            if gene_queries:
                combined = gene_queries[0].union(*gene_queries[1:]) if len(gene_queries) > 1 else gene_queries[0]
                total_genes = combined.distinct().count()
            else:
                total_genes = 0

            preclinical_datasets.append({
                "id": d.id,
                "name": d.name,
                "description": d.description,
				"software": d.software,
                "version": d.version,
                "link": d.link,
                "publication": d.publication,
                "PMID": d.PMID,
                "key_study_findings": d.key_study_findings,
                "total_samples": pc_samples.get(d.id, 0),
                "total_genes": total_genes,
                "total_drugs": pc_drugs.get(d.id, 0),
                "total_cell_lines": pc_cell_lines.get(d.id, 0),
                "data_layers": avail_layers,
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
    total_pre_clinical_datasets = session.query(Dataset).filter(Dataset.clinical == False).count()
    total_clinical_datasets = session.query(Dataset).filter(Dataset.clinical == True).count()
    total_pre_clinical_samples = session.query(PreClinicalSample.id).count()
    total_clinical_samples = session.query(ClinicalSample.id).count()
    total_drugs = session.query(func.count(distinct(PreClinicalTreatmentResponse.cid))).scalar()
    total_cell_lines = session.query(func.count(distinct(PreClinicalSample.cell_line_name))).scalar() or 0
    total_genes = session.query(PreClinicalGene.id).count()

    return {
        "total_clinical_datasets": total_clinical_datasets,
        "total_pre_clinical_datasets": total_pre_clinical_datasets,
        "total_pre_clinical_samples": total_pre_clinical_samples,
        "total_clinical_samples": total_clinical_samples,
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
    dataset = session.query(Dataset).filter(Dataset.id == dataset_id).first()
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
    clinical = get_clinical_status(dataset_id, session)

    if clinical:
        for data_layer_name, data_layer_model in clinical_data_layers.items():
            row = (
                session.query(data_layer_model.sample_id)
                .join(ClinicalSample, data_layer_model.sample_id == ClinicalSample.id)
                .filter(ClinicalSample.dataset_id == dataset_id)
                .first()
            )
            if row:
                available_layers.append(data_layer_name)
    else:
        # get the data layers available for the dataset by mapping sample ids to layers
        for data_layer_name, data_layer_model in pre_clinical_data_layers.items():
            if data_layer_name == "Treatment Response":
                row = (
                    session.query(data_layer_model.id)
                    .filter(data_layer_model.dataset_id == dataset_id)
                    .first()
                )
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
    clinical = get_clinical_status(dataset_id, session)

    if clinical:
        model = clinical_data_layers.get(molecular_profile)
        if not model:
            return []

        if molecular_profile == "RPPA":
            rows = (
                session.query(ClinicalAntigen.id, ClinicalAntigen.peptide_target)
                .all()
            )
            return [{"gene_id": row[0], "name": row[1] or row[0]} for row in rows]

        elif molecular_profile == "MiRNA":
            rows = (
                session.query(ClinicalMiRNA.id)
                .distinct()
                .all()
            )
            return [{"gene_id": row[0], "name": row[0]} for row in rows]

        elif molecular_profile == "Methylation":
            rows = (
                session.query(ClinicalProbe.id, ClinicalProbe.name)
                .all()
            )
            return [{"gene_id": row[0], "name": row[1] or row[0]} for row in rows]

        elif molecular_profile == "Mutation":
            gene_sub_query = (
                session.query(model.gene_id)
                .join(ClinicalSample, model.sample_id == ClinicalSample.id)
                .filter(ClinicalSample.dataset_id == dataset_id)
                .filter(model.gene_id.isnot(None))
                .distinct()
                .subquery()
            )
            rows = (
                session.query(gene_sub_query.c.gene_id, PreClinicalGene.name)
                .join(PreClinicalGene, PreClinicalGene.id == gene_sub_query.c.gene_id)
                .all()
            )

        else:
            # RNA-seq, CNV — whole-genome profiling covering all reference genes
            rows = (
                session.query(PreClinicalGene.id, PreClinicalGene.name)
                .all()
            )

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
    clinical = get_clinical_status(dataset_id, session)

    if clinical:
        # Clinical datasets do not currently have treatment response data
        return []
    else:
        rows = (
            session.query(PreClinicalTreatmentResponse.treatment_id, PreClinicalTreatmentResponse.cid)
            .filter(PreClinicalTreatmentResponse.dataset_id == dataset_id)
            .distinct(PreClinicalTreatmentResponse.treatment_id)
            .all()
        )

    rows = [{"treatment_id": row[0], "cid": row[1]} for row in rows]

    return rows

def get_clinical_status(dataset_id, session=Depends(get_db_session)):
    try:
        # deduce if dataset is clinical or pre clinical
        clinical = session.query(Dataset.clinical).filter(Dataset.id == dataset_id).scalar()
    except Exception as e:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return clinical


