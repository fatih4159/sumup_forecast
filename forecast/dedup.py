"""Canonical SumUp row identity: exact transaction/position when present, else normalized row."""
import hashlib
import json
import unicodedata

def normalize(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()

def row_fingerprint(row):
    # Include all source fields, including optional product / position identifiers.
    # Do not include import filename or upload timestamp: reimport must be idempotent.
    payload={normalize(k): normalize(v) for k,v in row.items() if not k.startswith("__")}
    canonical=json.dumps(payload,sort_keys=True,ensure_ascii=False,separators=(",",":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

def unique_rows(rows,existing_hashes):
    # Each indistinguishable line in a source file is a separate occurrence.
    # File reuploads can be detected by the deterministic row hash + occurrence.
    seen={}
    for row in rows:
        digest=row_fingerprint(row)
        seen[digest]=seen.get(digest,0)+1
        key=f"{digest}:{seen[digest]}"
        if key not in existing_hashes:
            yield key,row
