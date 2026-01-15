"""Base repository with common CRUD operations.

This module provides a generic base repository class that implements common
database operations (Create, Read, Update, Delete) for SQLAlchemy models.
All model-specific repositories should inherit from this class.
"""

from typing import Generic, TypeVar, Type, List, Any, Dict, Optional
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

# Type variable for SQLAlchemy models
ModelType = TypeVar("ModelType", bound=DeclarativeBase)


class BaseRepository(Generic[ModelType]):
    """
    Generic base repository for async CRUD operations.

    This class provides common database operations that work with any SQLAlchemy
    model. It uses generics to provide type safety while maintaining reusability.

    Attributes:
        model: The SQLAlchemy model class this repository manages
        session: The async database session for executing queries

    Type Parameters:
        ModelType: The SQLAlchemy model class (must inherit from DeclarativeBase)

    Usage:
        >>> class GameRepository(BaseRepository[Game]):
        ...     def __init__(self, session: AsyncSession):
        ...         super().__init__(Game, session)
        ...
        >>> async with AsyncSessionLocal() as session:
        ...     repo = GameRepository(session)
        ...     game = await repo.get_by_id(730)

    Design Notes:
        - All operations are async to support async SQLAlchemy
        - Uses generics for type safety without sacrificing reusability
        - Common operations provided: get, create, update, delete, list
        - Model-specific repositories can add custom queries
        - Does not auto-commit (caller controls transaction boundaries)
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository with model and database session.

        Args:
            model: The SQLAlchemy model class to manage
            session: The async database session

        Example:
            >>> repo = BaseRepository(Game, session)
        """
        self.model = model
        self.session = session

    async def get_by_id(self, id_value: Any) -> Optional[ModelType]:
        """
        Retrieve a single record by its primary key.

        Args:
            id_value: The primary key value to search for

        Returns:
            The model instance if found, None otherwise

        Example:
            >>> game = await repo.get_by_id(730)
            >>> if game:
            ...     print(game.name)
        """
        return await self.session.get(self.model, id_value)

    async def get_all(
        self, limit: Optional[int] = None, offset: Optional[int] = None
    ) -> List[ModelType]:
        """
        Retrieve all records with optional pagination.

        Args:
            limit: Maximum number of records to return (None for all)
            offset: Number of records to skip (default: 0)

        Returns:
            List of model instances

        Example:
            >>> # Get first 10 games
            >>> games = await repo.get_all(limit=10)
            >>> # Get next 10 games
            >>> games = await repo.get_all(limit=10, offset=10)
        """
        query = select(self.model)

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ModelType:
        """
        Create and persist a new record.

        Args:
            **kwargs: Field values for the new record

        Returns:
            The created model instance (not yet committed)

        Example:
            >>> game = await repo.create(
            ...     app_id=730,
            ...     name="Counter-Strike 2",
            ...     game_type="game"
            ... )
            >>> await session.commit()  # Caller commits transaction

        Note:
            This method does NOT commit the transaction. The caller must
            call session.commit() to persist changes to the database.
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()  # Flush to get auto-generated fields
        return instance

    async def update(self, id_value: Any, **kwargs) -> Optional[ModelType]:
        """
        Update an existing record by primary key.

        Args:
            id_value: The primary key of the record to update
            **kwargs: Field values to update

        Returns:
            The updated model instance if found, None otherwise

        Example:
            >>> game = await repo.update(
            ...     730,
            ...     name="Counter-Strike 2",
            ...     score=9.5
            ... )
            >>> if game:
            ...     await session.commit()

        Note:
            This method does NOT commit the transaction. The caller must
            call session.commit() to persist changes to the database.
        """
        instance = await self.get_by_id(id_value)
        if instance:
            for key, value in kwargs.items():
                setattr(instance, key, value)
            await self.session.flush()
            # Refresh to load server-side updated values (e.g., updated_at)
            await self.session.refresh(instance)
        return instance

    async def delete(self, id_value: Any) -> bool:
        """
        Delete a record by primary key.

        Args:
            id_value: The primary key of the record to delete

        Returns:
            True if record was deleted, False if not found

        Example:
            >>> deleted = await repo.delete(730)
            >>> if deleted:
            ...     await session.commit()

        Note:
            This method does NOT commit the transaction. The caller must
            call session.commit() to persist changes to the database.
        """
        instance = await self.get_by_id(id_value)
        if instance:
            await self.session.delete(instance)
            await self.session.flush()
            return True
        return False

    async def count(self) -> int:
        """
        Count total number of records.

        Returns:
            Total count of records in the table

        Example:
            >>> total_games = await repo.count()
            >>> print(f"Total games: {total_games}")
        """
        query = select(self.model)
        result = await self.session.execute(query)
        return len(result.scalars().all())

    async def exists(self, id_value: Any) -> bool:
        """
        Check if a record exists by primary key.

        Args:
            id_value: The primary key to check

        Returns:
            True if record exists, False otherwise

        Example:
            >>> if await repo.exists(730):
            ...     print("Game exists in database")
        """
        instance = await self.get_by_id(id_value)
        return instance is not None

    async def bulk_create(self, items: List[Dict[str, Any]]) -> List[ModelType]:
        """
        Create multiple records in a single operation.

        Args:
            items: List of dictionaries containing field values

        Returns:
            List of created model instances (not yet committed)

        Example:
            >>> games = await repo.bulk_create([
            ...     {"app_id": 730, "name": "CS2", "game_type": "game"},
            ...     {"app_id": 570, "name": "Dota 2", "game_type": "game"},
            ... ])
            >>> await session.commit()

        Note:
            This method does NOT commit the transaction. The caller must
            call session.commit() to persist changes to the database.
        """
        instances = [self.model(**item) for item in items]
        self.session.add_all(instances)
        await self.session.flush()
        return instances

    async def filter_by(self, **kwargs) -> List[ModelType]:
        """
        Filter records by field values.

        Args:
            **kwargs: Field name and value pairs to filter by

        Returns:
            List of matching model instances

        Example:
            >>> # Find all games of type "game"
            >>> games = await repo.filter_by(game_type="game")
            >>> # Find games with specific score
            >>> games = await repo.filter_by(score=9.5, game_type="game")
        """
        query = select(self.model).filter_by(**kwargs)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_one_or_none(self, **kwargs) -> Optional[ModelType]:
        """
        Get a single record matching the filter criteria.

        Args:
            **kwargs: Field name and value pairs to filter by

        Returns:
            The matching model instance if found, None otherwise

        Raises:
            MultipleResultsFound: If more than one record matches

        Example:
            >>> game = await repo.get_one_or_none(app_id=730)
            >>> if game:
            ...     print(game.name)
        """
        query = select(self.model).filter_by(**kwargs)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
