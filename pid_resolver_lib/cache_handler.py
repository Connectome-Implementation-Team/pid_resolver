from pathlib import Path
from typing import List, Dict, Union

from diskcache import Cache # type: ignore

CACHE_MAX_SIZE = int(4e9)


def get_keys(cache_dir: Path) -> List[str]:
    with Cache(directory=str(cache_dir), size_limit=CACHE_MAX_SIZE) as cache_ref:
        return list(cache_ref.iterkeys())


def write_record_to_cache(key: str, value: str, cache_dir: Path) -> None:
    with Cache(directory=str(cache_dir), size_limit=CACHE_MAX_SIZE) as cache_ref:
        cache_ref.set(key, value)


def write_records_to_cache(records: List, key: Union[str, int], value: Union[str, int], cache_dir: Path):
    with Cache(directory=str(cache_dir), size_limit=CACHE_MAX_SIZE) as cache_ref:
        for rec in records:
            write_record_to_cache(rec[key], rec[value], cache_dir)


def read_from_cache(key: str, cache_dir: Path) -> str:
    with Cache(directory=str(cache_dir), size_limit=CACHE_MAX_SIZE) as cache_ref:
        return cache_ref.get(key)

__all__ = ['get_keys', 'write_record_to_cache', 'read_from_cache', 'write_records_to_cache']