"""
DML SARLU - ERP On-Premise
==========================
Socle technique commun a tous les modeles.

Conventions imposees a l'ensemble de la base :
  * Cle primaire : UUID v4 (portabilite multi-sites, synchronisation offline)
  * Horodatage systematique (created_at / updated_at)
  * Suppression logique (soft delete) sur les referentiels sensibles
  * Piste d'audit (created_by / updated_by) sur les documents transactionnels
  * Convention de nommage des contraintes (indispensable pour Alembic)
  * Montants : Numeric(18, 2) -- Quantites : Numeric(18, 3)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from enum import Enum as PyEnum
from typing import Optional, Type

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    MetaData,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# ---------------------------------------------------------------------------
# Convention de nommage des contraintes (migrations Alembic deterministes)
# ---------------------------------------------------------------------------
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Classe de base declarative de l'ERP DML."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    def __repr__(self) -> str:  # pragma: no cover - confort de debug
        ident = getattr(self, "code", None) or getattr(self, "numero", None) or getattr(self, "id", None)
        return f"<{self.__class__.__name__} {ident}>"


# ---------------------------------------------------------------------------
# Helpers de typage
# ---------------------------------------------------------------------------
def EnumCol(enum_cls: Type[PyEnum], length: int = 50) -> SAEnum:
    """
    Colonne enumeree portable.

    native_enum=False -> stockage VARCHAR + CHECK constraint.
    Choix volontaire : evite les migrations douloureuses des types ENUM natifs
    PostgreSQL lorsqu'on ajoute une valeur metier (frequent sur un ERP vivant).
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        validate_strings=True,
        values_callable=lambda e: [m.value for m in e],
    )


Money = Numeric(18, 2)      # Montants en devise (XAF par defaut)
Quantity = Numeric(18, 3)   # Quantites (kg, tonnes, litres)
Rate = Numeric(7, 4)        # Taux, pourcentages, coefficients


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------
class UUIDMixin:
    """Cle primaire UUID v4."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )


class TimestampMixin:
    """Horodatage automatique de creation / modification."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=True,
    )


class SoftDeleteMixin:
    """Suppression logique : on n'efface JAMAIS une donnee comptable."""

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class AuditMixin:
    """
    Piste d'audit utilisateur.

    Volontairement limitee aux colonnes (pas de relationship) pour eviter
    les ambiguites de jointure multiples vers la table `utilisateurs`.
    La resolution se fait au niveau service / schema Pydantic.
    """

    @declared_attr
    def created_by_id(cls) -> Mapped[Optional[uuid.UUID]]:
        return mapped_column(
            Uuid(as_uuid=True),
            ForeignKey("utilisateurs.id", ondelete="SET NULL", use_alter=True),
            nullable=True,
            index=True,
        )

    @declared_attr
    def updated_by_id(cls) -> Mapped[Optional[uuid.UUID]]:
        return mapped_column(
            Uuid(as_uuid=True),
            ForeignKey("utilisateurs.id", ondelete="SET NULL", use_alter=True),
            nullable=True,
        )


class BaseModel(UUIDMixin, TimestampMixin, Base):
    """Modele de base : UUID + timestamps."""

    __abstract__ = True


class DocumentModel(UUIDMixin, TimestampMixin, AuditMixin, SoftDeleteMixin, Base):
    """
    Modele de base des documents transactionnels
    (bons, factures, mouvements, ecritures...) : UUID + timestamps + audit + soft delete.
    """

    __abstract__ = True


class ReferentielModel(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Modele de base des referentiels (clients, produits, magasins...)."""

    __abstract__ = True

    is_actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


__all__ = [
    "Base",
    "BaseModel",
    "DocumentModel",
    "ReferentielModel",
    "UUIDMixin",
    "TimestampMixin",
    "SoftDeleteMixin",
    "AuditMixin",
    "EnumCol",
    "Money",
    "Quantity",
    "Rate",
    "Decimal",
]
