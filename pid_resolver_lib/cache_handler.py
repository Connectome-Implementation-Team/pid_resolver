#  Copyright 2024 Switch
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

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