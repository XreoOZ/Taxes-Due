"""Frame-local entity index for fast household, workplace, and tile-neighbor queries."""

import math


class SpatialEntityIndex:
    def __init__(self, entities, tile_size):
        self.tile_size = max(1.0, float(tile_size))
        self._entities = list(entities or ())
        self._by_id = {}
        self._by_family = {}
        self._by_permit = {}
        self._by_tile = {}
        self._by_target_tile = {}
        self._locations = {}
        for entity in self._entities:
            self._index(entity)

    @staticmethod
    def _key(entity):
        return str(getattr(entity, "id", id(entity)))

    def _tile(self, x, y):
        return math.floor(x / self.tile_size), math.floor(y / self.tile_size)

    @staticmethod
    def _add(index, key, entity):
        if key is not None:
            index.setdefault(str(key), set()).add(entity)

    @staticmethod
    def _discard(index, key, entity):
        if key is None:
            return
        bucket = index.get(str(key))
        if bucket:
            bucket.discard(entity)
            if not bucket:
                index.pop(str(key), None)

    def _index(self, entity):
        key = self._key(entity)
        family_id = getattr(entity, "family_id", None)
        permit_id = getattr(entity, "assigned_permit_id", None)
        tile = self._tile(entity.x, entity.y)
        target = getattr(entity, "path_target_tile", None)
        target = tuple(target) if target else None
        self._by_id[key] = entity
        self._add(self._by_family, family_id, entity)
        self._add(self._by_permit, permit_id, entity)
        self._by_tile.setdefault(tile, set()).add(entity)
        if target is not None:
            self._by_target_tile.setdefault(target, set()).add(entity)
        self._locations[key] = (entity, family_id, permit_id, tile, target)

    def update(self, entity):
        """Refresh one actor after its state machine has moved or reassigned it."""
        key = self._key(entity)
        old = self._locations.get(key)
        if old:
            _, family_id, permit_id, tile, target = old
            self._discard(self._by_family, family_id, entity)
            self._discard(self._by_permit, permit_id, entity)
            target_bucket = self._by_target_tile.get(target)
            if target_bucket:
                target_bucket.discard(entity)
                if not target_bucket:
                    self._by_target_tile.pop(target, None)
            bucket = self._by_tile.get(tile)
            if bucket:
                bucket.discard(entity)
                if not bucket:
                    self._by_tile.pop(tile, None)
        self._index(entity)

    def by_id(self, entity_id):
        return self._by_id.get(str(entity_id))

    def by_ids(self, entity_ids):
        return [entity for entity_id in entity_ids or ()
                if (entity := self.by_id(entity_id)) is not None]

    def by_family(self, family_id):
        return tuple(self._by_family.get(str(family_id), ()))

    def by_permit(self, permit_id):
        return tuple(self._by_permit.get(str(permit_id), ()))

    def for_tiles(self, tiles, include_targets=True):
        entities = set()
        for tile in tiles or ():
            tile = tuple(tile)
            entities.update(self._by_tile.get(tile, ()))
            if include_targets:
                entities.update(self._by_target_tile.get(tile, ()))
        return entities

    def __iter__(self):
        return iter(self._entities)

    def __len__(self):
        return len(self._entities)

    def __bool__(self):
        return bool(self._entities)
