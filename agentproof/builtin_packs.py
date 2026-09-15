from __future__ import annotations

import base64
import gzip

from .models import EvalPack

# Deterministic 100-case synthetic fraud pack, gzip+base64 encoded to keep the repository compact.
_FRAUD_PACK_B64 = (
    "H4sIAMghqWoC/+2dS4/buhXH9/kUwqwnhPgm09XdFGiB9gLpXRQoLgzVVmbUeOypbGc6uMh3L+V5xPEMOUdHokU62SUjSqapv8nD"
    "33nwj3dFcdEsLj4UF5/aard4X62q5f1m+/4Lvbjsrq2qm7q7+ufuavHLw9Xil7ZeVcVTm0W9mbfN7bZZr7qmtCyLzf1qe11vm3kx"
    "r9rF+21brTbVvGvh/rCpN8Vds70urpvFol4VV+16t1oU23a3vSbF3+pqs2vrYlHPm013w3931bLZ3l8Wi2p1Vbu2m+JTtdzURXV7"
    "266/uH9eFstqW6/mrs187bpXuad9/PUv5KF722rzedasNu7586c+fqy/NPVd4fpYHPZtt2lWV8V6tbzfX9rsbm+XTb0oPtXV1vVp"
    "Q4qPtfvHqvjrP379+8N3eO5m3fWz2K4fu1VfFu3+Qy6LdVv8e7mef/5T0azmy92iLtb7wXLN28b1bTNfu+/bdbp13329euz3VVst"
    "6tb19g/3v+573N/uX8V/XJPZp6ZeLjb7hu5S6z68aevF058/FP/aX9i/nIf+Xez/8PvjDft2s7u6ubrebp4/4rD5h4KScv/Xr4/3"
    "uHfsXmi1nN00m5tqO7+uDz/o6QlPD+96+vywy28X6//d1vNtvb++H5XDi+41uEHsLj0O4sXjta8PvX/32JuLvYieP/2594dKLkv6"
    "/OiLbbNd7gfvt4O3/ds/3zNV2u8aNqvb3fZgQLp7v90ye/iAV27sOn/jZLyd1bvunWlNmD64eFO38+vKXZ47pV6t2/vuOe5bXM86"
    "FS3a6s5979fadwrp2i7Xd4fXV/XdbOH0Ne++1f7ncHBx3nWkvX9+Ua6JE/9hiy+1G3r3o5rR7qI6vHe32a7dp8/cD8pJfrao7ruB"
    "pqYsD1u5X/Xs1v0i6tX25dM/r9Z3q9nTV3jq4NOrfB7rAykcDPeBAl+o4Nv7rK4OxVcEx/Jo6I4e+vuhyD1KYlAlMaySmF9JpSGS"
    "vyWlq+rGTV0xFXTc5HsJsbclZNMW0MsRHK4bDtUNx+qGe3XDlaZERdbN0XvrLRv6tmw0XjXddYRoHtbtUTTz/aMgkhFQyQisZIRX"
    "MkoJokxCq9bgOYcr6ZfP8dPPbtmSUC1JrJakV0u2ZMTSt7TkHu3e6XQSonGXLeQE1EM/LwdwuGwUVDYKKxvllY0R6u1F65P70Rxt"
    "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"
)


def fraud_analyst_pack() -> EvalPack:
    payload = gzip.decompress(base64.b64decode(_FRAUD_PACK_B64)).decode("utf-8")
    return EvalPack.model_validate_json(payload)


def builtin_pack(pack_id: str) -> EvalPack | None:
    if pack_id == "fraud-analyst-v1":
        return fraud_analyst_pack()
    return None
