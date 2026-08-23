from sys import version
from sqlalchemy import (
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


"""
Pre-clinical tables: tables related to the storage/organization of data from
in vitro datasets.
"""


class Datasets(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    version: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    link: Mapped[str] = mapped_column(String(255), nullable=False)
    publication: Mapped[str] = mapped_column(String(255), nullable=False) # publication year
    PMID: Mapped[str] = mapped_column(String(20), nullable=False)
    key_study_findings: Mapped[str] = mapped_column(String(255), nullable=False)
    clinical: Mapped[bool] = mapped_column(Boolean, nullable=False)

    cell_lines: Mapped[list["PreClinicalCellLine"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )
    samples: Mapped[list["PreClinicalSample"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        overlaps="cell_line,samples",
    )
    treatment_responses: Mapped[list["PreClinicalTreatmentResponse"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        overlaps="cell_line,treatment_responses",
    )


class PreClinicalCellLine(Base):
    __tablename__ = "pre_clinical_cell_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pre_clinical_dataset.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Fields from pre_clinical_cell_line.csv.
    cell_line_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tissueid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mod_tissueid: Mapped[str | None] = mapped_column(String(255), nullable=True)
    accession: Mapped[str | None] = mapped_column(String(255), nullable=True)
    category: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sex: Mapped[str | None] = mapped_column(String(30), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "cell_line_name",
            "dataset_id",
            name="uq_pc_cell_line_dataset",
        ),
    )

    dataset: Mapped["Datasets"] = relationship(back_populates="cell_lines")
    samples: Mapped[list["PreClinicalSample"]] = relationship(
        back_populates="cell_line",
        cascade="all, delete-orphan",
        overlaps="dataset,samples",
    )
    treatment_responses: Mapped[list["PreClinicalTreatmentResponse"]] = relationship(
        back_populates="cell_line",
        cascade="all, delete-orphan",
        overlaps="dataset,treatment_responses",
    )


class PreClinicalSample(Base):
    __tablename__ = "pre_clinical_sample"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pre_clinical_dataset.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Store the human-readable cell-line key directly. The composite FK below
    # enforces that (cell_line_name, dataset_id) exists in pre_clinical_cell_line.
    cell_line_name: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["cell_line_name", "dataset_id"],
            [
                "pre_clinical_cell_line.cell_line_name",
                "pre_clinical_cell_line.dataset_id",
            ],
            ondelete="CASCADE",
            name="fk_pc_sample_cell_line_dataset",
        ),
        UniqueConstraint(
            "id",
            "dataset_id",
            name="uq_pc_sample_dataset",
        ),
    )

    dataset: Mapped["Datasets"] = relationship(
        back_populates="samples",
        overlaps="cell_line,samples",
    )
    cell_line: Mapped["PreClinicalCellLine"] = relationship(
        back_populates="samples",
        overlaps="dataset,samples,cell_lines",
    )

    rna_seq_data: Mapped[list["PreClinicalRnaSeq"]] = relationship(
        back_populates="sample",
        cascade="all, delete-orphan",
    )
    microarray_data: Mapped[list["PreClinicalMicroarray"]] = relationship(
        back_populates="sample",
        cascade="all, delete-orphan",
    )
    copy_number_variations: Mapped[list["PreClinicalCopyNumberVariation"]] = relationship(
        back_populates="sample",
        cascade="all, delete-orphan",
    )
    mutations: Mapped[list["PreClinicalMutation"]] = relationship(
        back_populates="sample",
        cascade="all, delete-orphan",
    )


class PreClinicalTreatmentResponse(Base):
    __tablename__ = "pre_clinical_treatment_response"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("pre_clinical_dataset.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Store the human-readable cell-line key directly. The composite FK below
    # enforces that (cell_line_name, dataset_id) exists in pre_clinical_cell_line.
    cell_line_name: Mapped[str] = mapped_column(String(255), nullable=False)

    treatment_id: Mapped[str] = mapped_column(String(255), nullable=False)
    ic50_recomputed: Mapped[float | None] = mapped_column(Float, nullable=True)
    acc_recomputed: Mapped[float | None] = mapped_column(Float, nullable=True)
    mechanism_of_action: Mapped[str | None] = mapped_column(String(255), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["cell_line_name", "dataset_id"],
            [
                "pre_clinical_cell_line.cell_line_name",
                "pre_clinical_cell_line.dataset_id",
            ],
            ondelete="CASCADE",
            name="fk_pc_tr_cell_line_dataset",
        ),
        UniqueConstraint(
            "dataset_id",
            "cell_line_name",
            "treatment_id",
            name="uq_pc_tr_dataset_cell_line_treatment",
        ),
    )

    dataset: Mapped["Datasets"] = relationship(
        back_populates="treatment_responses",
        overlaps="cell_line,treatment_responses",
    )
    cell_line: Mapped["PreClinicalCellLine"] = relationship(
        back_populates="treatment_responses",
        overlaps="dataset,treatment_responses",
    )


class PreClinicalGene(Base):
    __tablename__ = "pre_clinical_gene"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)


class PreClinicalRnaSeq(Base):
    __tablename__ = "pre_clinical_rna_seq"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sample_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("pre_clinical_sample.id", ondelete="CASCADE"),
        nullable=False,
    )
    gene_id: Mapped[str] = mapped_column(String(255), nullable=False)
    expression_value: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "sample_id",
            "gene_id",
            name="uq_pc_rna_sample_gene",
        ),
    )

    sample: Mapped["PreClinicalSample"] = relationship(back_populates="rna_seq_data")


class PreClinicalMicroarray(Base):
    __tablename__ = "pre_clinical_microarray"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sample_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("pre_clinical_sample.id", ondelete="CASCADE"),
        nullable=False,
    )
    gene_id: Mapped[str] = mapped_column(String(255), nullable=False)
    expression_value: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "sample_id",
            "gene_id",
            name="uq_pc_microarray_sample_gene",
        ),
    )

    sample: Mapped["PreClinicalSample"] = relationship(back_populates="microarray_data")


class PreClinicalCopyNumberVariation(Base):
    __tablename__ = "pre_clinical_copy_number_variation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sample_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("pre_clinical_sample.id", ondelete="CASCADE"),
        nullable=False,
    )
    gene_id: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "sample_id",
            "gene_id",
            name="uq_pc_cnv_sample_gene",
        ),
    )

    sample: Mapped["PreClinicalSample"] = relationship(
        back_populates="copy_number_variations"
    )


class PreClinicalMutation(Base):
    __tablename__ = "pre_clinical_mutation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sample_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("pre_clinical_sample.id", ondelete="CASCADE"),
        nullable=False,
    )
    gene_id: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(255), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "sample_id",
            "gene_id",
            name="uq_pc_mutation_sample_gene",
        ),
    )

    sample: Mapped["PreClinicalSample"] = relationship(back_populates="mutations")