"""The Merkle tree of RFC 6962, Certificate Transparency's (D-060).

One root that depends on every leaf, and for any one leaf a short proof (its
"audit path") that it is in the tree. Following the RFC exactly means the
published test vectors apply, and so does every tool and paper written for
Certificate Transparency.

    leaf hash = SHA-256(0x00 || leaf)
    node hash = SHA-256(0x01 || left || right)
    empty tree = SHA-256("")

The distinct prefixes stop a leaf being passed off as an inner node. A tree
of n leaves splits at the largest power of two smaller than n.
"""

import hashlib
from collections.abc import Sequence


def leaf_hash(leaf: bytes) -> bytes:
    return hashlib.sha256(b"\x00" + leaf).digest()


def node_hash(left: bytes, right: bytes) -> bytes:
    return hashlib.sha256(b"\x01" + left + right).digest()


def _split(n: int) -> int:
    """The largest power of two smaller than n (n >= 2)."""
    k = 1
    while k * 2 < n:
        k *= 2
    return k


def root(leaves: Sequence[bytes]) -> bytes:
    """MTH(D[n]), RFC 6962 section 2.1."""
    if not leaves:
        return hashlib.sha256(b"").digest()
    if len(leaves) == 1:
        return leaf_hash(leaves[0])
    k = _split(len(leaves))
    return node_hash(root(leaves[:k]), root(leaves[k:]))


def audit_path(index: int, leaves: Sequence[bytes]) -> list[bytes]:
    """PATH(m, D[n]), RFC 6962 section 2.1.1: the siblings from leaf to root."""
    if not 0 <= index < len(leaves):
        raise IndexError("no leaf at that index")
    if len(leaves) == 1:
        return []
    k = _split(len(leaves))
    if index < k:
        return [*audit_path(index, leaves[:k]), root(leaves[k:])]
    return [*audit_path(index - k, leaves[k:]), root(leaves[:k])]


def root_from_path(index: int, size: int, leaf: bytes, path: Sequence[bytes]) -> bytes:
    """Recompute the root from one leaf and its audit path (RFC 9162 section 2.1.3.2).

    A proof is good when this equals the published root.
    """
    if not 0 <= index < size:
        raise ValueError("index outside the tree")
    fn, sn = index, size - 1
    result = leaf_hash(leaf)
    for sibling in path:
        if sn == 0:
            raise ValueError("path is longer than the tree is deep")
        if fn & 1 or fn == sn:
            result = node_hash(sibling, result)
            while not fn & 1 and fn != 0:
                fn >>= 1
                sn >>= 1
        else:
            result = node_hash(result, sibling)
        fn >>= 1
        sn >>= 1
    if sn != 0:
        raise ValueError("path is shorter than the tree is deep")
    return result
