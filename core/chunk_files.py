import re
from pathlib import Path

_CHUNK_NAME = re.compile(r"chunk_\d{8}_\d{6}(?:_\d{6})?\.(mp4|json)")


def chunk_files(directory):
    if directory.is_dir():
        for path in directory.iterdir():
            if _CHUNK_NAME.fullmatch(path.name) and path.is_file():
                yield path


def protected_chunk_files(storage):
    with storage._get_connection() as conn:
        records = conn.execute(
            "SELECT file_path, window_records_path FROM chunks WHERE status <> 'completed'"
        ).fetchall()
    return {Path(path).resolve() for record in records for path in record if path}
