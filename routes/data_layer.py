import io
import os
from collections import defaultdict
from typing import List
from urllib.parse import quote_plus
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import create_engine, select, or_, and_, func
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw
from sklearn.decomposition import PCA
from sklearn.cluster import MiniBatchKMeans

from database_session import get_db_session
from models.tables import (
    Dataset,
    PreClinicalSample,
    PreClinicalCellLine,
    PreClinicalCellLineInfo,
    PreClinicalGene,
    PreClinicalTreatmentResponse,
    PreClinicalDrug,
    ClinicalSample,
    ClinicalAntigen,
    ClinicalProbe,
    ClinicalSlide,
    ClinicalTile,
    ClinicalEmbedding,
)
from models.data_layers import pre_clinical_molecular_layers, clinical_molecular_layers

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

    dataset = session.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if dataset.clinical:
        data_layer_model = clinical_molecular_layers.get(molecular_profile)
        if not data_layer_model:
            raise HTTPException(
                status_code=404, detail="Molecular profiles not found for this dataset"
            )
        try:
            if molecular_profile in ("RNA-seq", "Copy Number Variation"):
                rows = (
                    session.query(
                        PreClinicalGene.name.label("gene_name"),
                        ClinicalSample.id.label("sample"),
                        ClinicalSample.tissue.label("tissue"),
                        ClinicalSample.histology.label("histology"),
                        data_layer_model.value,
                        ClinicalSample.race,
                        ClinicalSample.sex,
                        ClinicalSample.age,
                    )
                    .join(ClinicalSample, data_layer_model.sample_id == ClinicalSample.id)
                    .join(PreClinicalGene, PreClinicalGene.id == data_layer_model.gene_id)
                    .filter(ClinicalSample.dataset_id == dataset_id)
                    .filter(data_layer_model.gene_id.in_(gene))
                    .all()
                )
                for gene_name, sample, tissue, histology, value, race, sex, age in rows:
                    result[gene_name].append({
                        "sample": sample,
                        "value": value,
                        "tissue": tissue,
                        "histology": histology,
                        "race": race,
                        "sex": sex,
                        "age": age,
                    })

            elif molecular_profile == "Mutation":
                rows = (
                    session.query(
                        PreClinicalGene.name.label("gene_name"),
                        ClinicalSample.id.label("sample"),
                        ClinicalSample.tissue.label("tissue"),
                        ClinicalSample.histology.label("histology"),
                        data_layer_model.mutation,
                        data_layer_model.oncoprint,
                        ClinicalSample.race,
                        ClinicalSample.sex,
                        ClinicalSample.age,
                    )
                    .join(ClinicalSample, data_layer_model.sample_id == ClinicalSample.id)
                    .join(PreClinicalGene, PreClinicalGene.id == data_layer_model.gene_id)
                    .filter(ClinicalSample.dataset_id == dataset_id)
                    .filter(data_layer_model.gene_id.in_(gene))
                    .all()
                )
                for gene_name, sample, tissue, histology, mutation, oncoprint, race, sex, age in rows:
                    result[gene_name].append({
                        "sample": sample,
                        "mutation": mutation,
                        "oncoprint": oncoprint,
                        "tissue": tissue,
                        "histology": histology,
                        "race": race,
                        "sex": sex,
                        "age": age,
                    })

            elif molecular_profile == "RPPA":
                rows = (
                    session.query(
                        ClinicalAntigen.id.label("antigen_id"),
                        ClinicalAntigen.peptide_target,
                        ClinicalAntigen.peptide_target_gene,
                        ClinicalSample.id.label("sample"),
                        ClinicalSample.tissue.label("tissue"),
                        ClinicalSample.histology.label("histology"),
                        data_layer_model.value,
                        ClinicalSample.race,
                        ClinicalSample.sex,
                        ClinicalSample.age,
                    )
                    .join(ClinicalSample, data_layer_model.sample_id == ClinicalSample.id)
                    .join(ClinicalAntigen, ClinicalAntigen.id == data_layer_model.antigen_id)
                    .filter(ClinicalSample.dataset_id == dataset_id)
                    .filter(data_layer_model.antigen_id.in_(gene))
                    .all()
                )
                for antigen_id, peptide_target, peptide_target_gene, sample, tissue, histology, value, race, sex, age in rows:
                    key = peptide_target or antigen_id
                    result[key].append({
                        "sample": sample,
                        "value": value,
                        "tissue": tissue,
                        "histology": histology,
                        "antigen_id": antigen_id,
                        "peptide_target": peptide_target,
                        "peptide_target_gene": peptide_target_gene,
                        "race": race,
                        "sex": sex,
                        "age": age,
                    })

            elif molecular_profile == "MiRNA":
                rows = (
                    session.query(
                        data_layer_model.id.label("mirna_id"),
                        ClinicalSample.id.label("sample"),
                        ClinicalSample.tissue.label("tissue"),
                        ClinicalSample.histology.label("histology"),
                        data_layer_model.value,
                        ClinicalSample.race,
                        ClinicalSample.sex,
                        ClinicalSample.age,
                    )
                    .join(ClinicalSample, data_layer_model.sample_id == ClinicalSample.id)
                    .filter(ClinicalSample.dataset_id == dataset_id)
                    .filter(data_layer_model.id.in_(gene))
                    .all()
                )
                for mirna_id, sample, tissue, histology, value, race, sex, age in rows:
                    result[mirna_id].append({
                        "sample": sample,
                        "value": value,
                        "tissue": tissue,
                        "histology": histology,
                        "race": race,
                        "sex": sex,
                        "age": age,
                    })

            elif molecular_profile == "Methylation":
                rows = (
                    session.query(
                        data_layer_model.probe_id,
                        ClinicalProbe.name.label("probe_name"),
                        ClinicalSample.id.label("sample"),
                        ClinicalSample.tissue.label("tissue"),
                        ClinicalSample.histology.label("histology"),
                        data_layer_model.value,
                        ClinicalSample.race,
                        ClinicalSample.sex,
                        ClinicalSample.age,
                    )
                    .join(ClinicalSample, data_layer_model.sample_id == ClinicalSample.id)
                    .join(ClinicalProbe, ClinicalProbe.id == data_layer_model.probe_id)
                    .filter(ClinicalSample.dataset_id == dataset_id)
                    .filter(data_layer_model.probe_id.in_(gene))
                    .all()
                )
                for probe_id, probe_name, sample, tissue, histology, value, race, sex, age in rows:
                    key = probe_name or probe_id
                    result[key].append({
                        "sample": sample,
                        "value": value,
                        "tissue": tissue,
                        "histology": histology,
                        "probe_id": probe_id,
                        "probe_name": probe_name,
                        "race": race,
                        "sex": sex,
                        "age": age,
                    })

        except Exception as e:
            print(f"Error querying clinical molecular profile for {molecular_profile} (dataset_id={dataset_id}): {e}")
            raise HTTPException(
                status_code=404, detail=f"Molecular profile '{molecular_profile}' error: {e}"
            )

    else:
        data_layer_model = pre_clinical_molecular_layers.get(molecular_profile)
        if not data_layer_model:
            raise HTTPException(
                status_code=404, detail="Molecular profile not found for this dataset"
           )
        try:
            rows = (
                session.query(
                    PreClinicalGene.name.label("gene_name"),
                    PreClinicalSample.cell_line_name.label("cell_line"),
                    PreClinicalCellLine.tissueid.label("tissue"),
                    data_layer_model.value,
                    PreClinicalCellLine.sex,
                    PreClinicalCellLine.age,
                    PreClinicalCellLineInfo.second_level,
                    PreClinicalCellLineInfo.disease_descriptions,
                )
                .join(PreClinicalSample, data_layer_model.sample_id == PreClinicalSample.id)
                .join(
                    PreClinicalCellLine,
                    and_(
                        PreClinicalSample.cell_line_name == PreClinicalCellLine.cell_line_name,
                        PreClinicalSample.dataset_id == PreClinicalCellLine.dataset_id,
                    ),
                )
                .outerjoin(
                    PreClinicalCellLineInfo,
                    PreClinicalCellLine.accession == PreClinicalCellLineInfo.accession,
                )
                .join(PreClinicalGene, PreClinicalGene.id == data_layer_model.gene_id)
                .filter(PreClinicalSample.dataset_id == dataset_id)
                .filter(data_layer_model.gene_id.in_(gene))
                .all()
            )
            for gene_name, cell_line, tissue, value, sex, age, second_level, disease_descriptions in rows:
                result[gene_name].append({
                    "cellLine": cell_line,
                    "value": value,
                    "tissue": tissue,
                    "sex": sex,
                    "age": age,
                    "second_level": second_level,
                    "disease_descriptions": disease_descriptions,
                })
        except Exception as e:
            print(f"Error querying molecular profile for {molecular_profile} (dataset_id={dataset_id}): {e}")
            raise HTTPException(
                status_code=404, detail=f"Molecular profile '{molecular_profile}' error: {e}"
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

    dataset = session.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    result = defaultdict(list)
    drug_list = [d.strip() for d in drug if d and d.strip()]

    if dataset.clinical:
        raise HTTPException(
            status_code=404,
            detail="Treatment response data is not available for clinical datasets"
        )

    else:
        try:
            query = (
                session.query(
                    PreClinicalTreatmentResponse.treatment_id.label("drug_name"),
                    PreClinicalTreatmentResponse.cell_line_name.label("cell_line"),
                    PreClinicalCellLine.tissueid.label("tissue"),
                    PreClinicalTreatmentResponse.cid,
                    PreClinicalTreatmentResponse.ic50_recomputed,
                    PreClinicalTreatmentResponse.acc_recomputed,
                    PreClinicalCellLine.sex,
                    PreClinicalCellLine.age,
                    PreClinicalCellLineInfo.second_level,
                    PreClinicalCellLineInfo.disease_descriptions,
                    PreClinicalDrug.fda_approval,
                    PreClinicalDrug.mechanism_action_type,
                    PreClinicalDrug.mechanism_of_action,
                )
                .join(
                    PreClinicalCellLine,
                    and_(
                        PreClinicalTreatmentResponse.cell_line_name == PreClinicalCellLine.cell_line_name,
                        PreClinicalTreatmentResponse.dataset_id == PreClinicalCellLine.dataset_id,
                    ),
                )
                .outerjoin(
                    PreClinicalCellLineInfo,
                    PreClinicalCellLine.accession == PreClinicalCellLineInfo.accession,
                )
                .outerjoin(
                    PreClinicalDrug,
                    PreClinicalTreatmentResponse.cid == PreClinicalDrug.cid,
                )
                .filter(PreClinicalTreatmentResponse.dataset_id == dataset_id)
            )

            if drug_list:
                query = query.filter(PreClinicalTreatmentResponse.treatment_id.in_(drug_list))

            rows = query.all()
            for drug_name, cell_line, tissue, cid, ic50_recomputed, acc_recomputed, sex, age, second_level, disease_descriptions, fda_approval, mechanism_action_type, mechanism_of_action in rows:
                result[drug_name].append({
                    "cellLine": cell_line,
                    "ic50_recomputed": ic50_recomputed,
                    "aac_recomputed": acc_recomputed,
                    "tissue": tissue,
                    "cid": cid,
                    "sex": sex,
                    "age": age,
                    "second_level": second_level,
                    "disease_descriptions": disease_descriptions,
                    "fda_approval": fda_approval,
                    "mechanism_action_type": mechanism_action_type,
                    "mechanism_of_action": mechanism_of_action,
                })
        except Exception as e:
            print(f"Error querying treatment response (dataset_id={dataset_id}): {e}")
            raise HTTPException(
                status_code=404, detail=f"Treatment response error: {e}"
            )

    return result


SVS_STORAGE_PATH = os.getenv("SVS_STORAGE_PATH", "/mnt/slides")
TILE_CACHE_DIR = os.getenv("TILE_CACHE_DIR", "/tmp/sts_tile_cache")


def l2norm(X: np.ndarray) -> np.ndarray:
    """L2-normalize rows of feature matrix (reused from leiden_archetypes_resection.py)."""
    n = np.linalg.norm(X, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return X / n


def create_placeholder_tile(slide_id: str, x: int, y: int, size: int = 512) -> io.BytesIO:
    """Generate a clean visual placeholder tile when physical .svs is not yet mounted."""
    img = Image.new("RGB", (size, size), color=(244, 246, 248))
    draw = ImageDraw.Draw(img)

    # Frame border
    draw.rectangle([0, 0, size - 1, size - 1], outline=(203, 213, 225), width=3)
    # Subtle inner grid
    for step in range(64, size, 64):
        draw.line([(step, 0), (step, size)], fill=(235, 240, 245), width=1)
        draw.line([(0, step), (size, step)], fill=(235, 240, 245), width=1)

    lines = [
        "H&E Tile Preview",
        f"Slide: {slide_id}",
        f"Coord: (X: {x}, Y: {y})",
        f"Size: {size}x{size} px"
    ]

    y_pos = 130
    for line in lines:
        if line.startswith("["):
            color = (37, 99, 235)  # blue
        elif "Preview" in line:
            color = (15, 23, 42)   # dark slate
        else:
            color = (71, 85, 105)  # muted slate
        draw.text((size // 2, y_pos), line, fill=color, anchor="mm")
        y_pos += 30

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return buf


def find_svs_file(slide_id: str) -> str | None:
    """Locate the .svs file across possible FUSE mount paths and subdirectories."""
    clean_id = os.path.basename(slide_id).replace(".svs", "")

    # Common mount search directories
    search_dirs = [
        SVS_STORAGE_PATH,
        os.path.join(SVS_STORAGE_PATH, "TCGA_SARC"),
        "/mnt/slides",
        "/mnt/slides/TCGA_SARC",
        os.path.expanduser("~/mnt/slides"),
        os.path.expanduser("~/mnt/slides/TCGA_SARC"),
        "./slides",
        "./slides/TCGA_SARC",
    ]

    for base_dir in search_dirs:
        if not os.path.isdir(base_dir):
            continue

        # 1. Exact match: {clean_id}.svs
        exact_path = os.path.join(base_dir, f"{clean_id}.svs")
        if os.path.isfile(exact_path):
            return exact_path

        # 2. Match with barcode suffix: {clean_id}_Surgical_Resection.svs
        alt_path = os.path.join(base_dir, f"{clean_id}_Surgical_Resection.svs")
        if os.path.isfile(alt_path):
            return alt_path

        # 3. Search directory for matching prefix or UUID
        try:
            for f in os.listdir(base_dir):
                if f.endswith(".svs"):
                    f_name = f.replace(".svs", "")
                    if clean_id == f_name or clean_id.startswith(f_name) or f_name.startswith(clean_id):
                        return os.path.join(base_dir, f)
                    if "." in clean_id:
                        barcode, uuid = clean_id.split(".", 1)
                        if barcode in f or uuid in f:
                            return os.path.join(base_dir, f)
        except Exception:
            pass

    return None


def extract_tile_from_svs(slide_id: str, x: int, y: int, size: int = 512) -> io.BytesIO | None:
    """Crop a region from SVS file via OpenSlide with local disk caching."""
    # 1. Check local tile cache first
    cache_filepath = None
    try:
        os.makedirs(TILE_CACHE_DIR, exist_ok=True)
        cache_filename = f"{slide_id}_{x}_{y}_{size}.jpg".replace("/", "_")
        cache_filepath = os.path.join(TILE_CACHE_DIR, cache_filename)
        if os.path.isfile(cache_filepath) and os.path.getsize(cache_filepath) > 0:
            with open(cache_filepath, "rb") as f:
                return io.BytesIO(f.read())
    except Exception as e:
        print(f"Cache check warning: {e}")

    # 2. Locate SVS file on FUSE mount
    svs_file = find_svs_file(slide_id)
    if not svs_file or not os.path.isfile(svs_file):
        return None

    # 3. Read region via OpenSlide
    try:
        import openslide
        slide = openslide.OpenSlide(svs_file)
        tile = slide.read_region((int(x), int(y)), 0, (int(size), int(size))).convert("RGB")
        slide.close()

        buf = io.BytesIO()
        tile.save(buf, format="JPEG", quality=90)
        buf.seek(0)

        # Save to disk cache for instantaneous re-requests
        if cache_filepath:
            try:
                with open(cache_filepath, "wb") as f:
                    f.write(buf.getvalue())
            except Exception:
                pass

        return buf
    except Exception as e:
        print(f"OpenSlide tile extraction error for {slide_id} ({x}, {y}) from {svs_file}: {e}")
        return None


@router.get(
    "/imaging/clustering",
    summary="Compute 2D latent space and clusters for subsampled H&E tile embeddings",
)
async def get_imaging_clustering(
    dataset_id: int = Query(..., description="Dataset ID to pull H&E imaging data from", example=6),
    sample_size: int = Query(5000, description="Max tiles to subsample across dataset"),
    n_clusters: int = Query(10, description="Number of clusters / archetypes"),
    session=Depends(get_db_session),
):
    dataset = session.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")

    if not dataset.clinical:
        raise HTTPException(
            status_code=400,
            detail="H&E imaging data is only available for clinical datasets"
        )

    try:
        # 1. Fetch all slide IDs belonging to this dataset
        slide_rows = (
            session.query(ClinicalSlide.id, ClinicalSlide.sample_id, ClinicalSlide.n_tiles)
            .filter(ClinicalSlide.dataset_id == dataset_id)
            .all()
        )
        if not slide_rows:
            raise HTTPException(
                status_code=404,
                detail=f"No clinical slides found for dataset {dataset_id}"
            )

        slide_ids = [r[0] for r in slide_rows]
        n_slides = len(slide_rows)
        tiles_per_slide = max(5, min(25, sample_size // n_slides))

        # Query up to `tiles_per_slide` from EVERY slide across the dataset using indexed slide_id
        query = (
            session.query(
                ClinicalTile.id.label("tile_id"),
                ClinicalTile.slide_id,
                ClinicalTile.tile_index,
                ClinicalTile.x,
                ClinicalTile.y,
                ClinicalSample.id.label("patient_id"),
                ClinicalSample.histology,
                ClinicalSample.tissue,
                ClinicalSample.race,
                ClinicalSample.sex,
                ClinicalSample.age,
                ClinicalEmbedding.embedding,
            )
            .join(ClinicalSlide, ClinicalSlide.id == ClinicalTile.slide_id)
            .join(ClinicalSample, ClinicalSample.id == ClinicalSlide.sample_id)
            .join(
                ClinicalEmbedding,
                and_(
                    ClinicalEmbedding.slide_id == ClinicalTile.slide_id,
                    ClinicalEmbedding.tile_id == ClinicalTile.id,
                ),
            )
            .filter(ClinicalSlide.dataset_id == dataset_id)
            .filter(ClinicalTile.slide_id.in_(slide_ids))
            .filter(ClinicalEmbedding.slide_id.in_(slide_ids))
            .filter(ClinicalTile.tile_index < tiles_per_slide)
            .filter(ClinicalEmbedding.kind == "tile")
        )
        rows = query.all()
        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No tile embeddings found in dataset {dataset_id}"
            )

        # 1. Unpack binary float32 embeddings (1536-d)
        X = np.vstack([np.frombuffer(r.embedding, dtype=np.float32) for r in rows])

        # 2. L2-Normalize (cosine geometry on unit sphere)
        X_norm = l2norm(X)

        # 3. PCA 1536 -> 128 components
        n_pc = min(128, X_norm.shape[0], X_norm.shape[1])
        pca = PCA(n_components=n_pc, random_state=42)
        Xp = pca.fit_transform(X_norm).astype(np.float32)

        # 4. MiniBatchKMeans / Centroid discovery
        k = max(2, min(n_clusters, len(Xp)))
        kmeans = MiniBatchKMeans(n_clusters=k, random_state=42, batch_size=min(1024, len(Xp)))
        cluster_labels = kmeans.fit_predict(Xp)
        centroids = kmeans.cluster_centers_

        # 5. Top 2 Principal Components for 2D Scatter visualization
        umap1 = Xp[:, 0]
        umap2 = Xp[:, 1] if Xp.shape[1] > 1 else np.zeros_like(umap1)

        # 6. Euclidean distance to cluster centroid
        distances = np.linalg.norm(Xp - centroids[cluster_labels], axis=1)

        points = []
        cluster_tile_map = defaultdict(list)

        for i, r in enumerate(rows):
            cid = int(cluster_labels[i])
            cname = f"Cluster {cid}"
            dist = float(distances[i])

            point_data = {
                "tile_id": int(r.tile_id),
                "slide_id": str(r.slide_id),
                "patient_id": str(r.patient_id),
                "tile_index": int(r.tile_index) if r.tile_index is not None else i,
                "x": float(r.x),
                "y": float(r.y),
                "umap1": float(umap1[i]),
                "umap2": float(umap2[i]),
                "cluster_id": cid,
                "cluster": cname,
                "dist_to_centroid": dist,
                "histology": r.histology or "Unknown",
                "tissue": r.tissue or "Soft Tissue",
                "race": r.race,
                "sex": r.sex,
                "age": r.age,
                "crop_url": f"/api/data-layer/imaging/tile-crop?slide_id={r.slide_id}&x={int(r.x)}&y={int(r.y)}&size=512",
            }
            points.append(point_data)
            cluster_tile_map[cid].append((dist, point_data))

        # 7. Build cluster summaries & pick top 12 exemplar tiles per cluster
        clusters = []
        for cid in range(k):
            cname = f"Cluster {cid}"
            tiles_in_cluster = cluster_tile_map.get(cid, [])
            tiles_in_cluster.sort(key=lambda item: item[0])  # rank by dist_to_centroid ascending

            seen_patients = set()
            exemplars = []
            # Round 1: Diversify by unique patients
            for dist, p in tiles_in_cluster:
                if p["patient_id"] not in seen_patients:
                    exemplars.append(p)
                    seen_patients.add(p["patient_id"])
                if len(exemplars) >= 12:
                    break

            # Round 2: Fill remaining slots up to 12
            if len(exemplars) < 12:
                for dist, p in tiles_in_cluster:
                    if p not in exemplars:
                        exemplars.append(p)
                    if len(exemplars) >= 12:
                        break

            histologies = [p["histology"] for _, p in tiles_in_cluster if p["histology"]]
            dominant_hist = max(set(histologies), key=histologies.count) if histologies else "N/A"

            clusters.append({
                "cluster_id": cid,
                "name": cname,
                "tile_count": len(tiles_in_cluster),
                "patient_count": len(set(p["patient_id"] for _, p in tiles_in_cluster)),
                "dominant_histology": dominant_hist,
                "exemplars": exemplars,
            })

        return {
            "points": points,
            "clusters": clusters,
            "total_tiles": len(points),
            "n_clusters": k,
        }

    except Exception as e:
        print(f"Error in get_imaging_clustering (dataset_id={dataset_id}): {e}")
        raise HTTPException(status_code=500, detail=f"Imaging clustering error: {str(e)}")


@router.get(
    "/imaging/tile-crop",
    summary="On-demand 512x512 tile crop from .svs whole slide image via FUSE mount",
)
async def crop_tile_image(
    slide_id: str = Query(..., description="Slide barcode / ID"),
    x: int = Query(..., description="Top-left Level 0 X coordinate"),
    y: int = Query(..., description="Top-left Level 0 Y coordinate"),
    size: int = Query(512, description="Crop size in pixels"),
):
    buf = extract_tile_from_svs(slide_id, x, y, size)
    if buf is None:
        buf = create_placeholder_tile(slide_id, x, y, size)

    return StreamingResponse(
        buf,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=604800, immutable",
        },
    )

