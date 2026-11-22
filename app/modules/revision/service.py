from app.modules.delivery.checks import verify
from app.modules.runs.service import KIND_REVISION, record


def revise(store, base_key, material):
    base = store.read(base_key)
    verify(base, store)
    return record(store, material, kind=KIND_REVISION, base=base)
