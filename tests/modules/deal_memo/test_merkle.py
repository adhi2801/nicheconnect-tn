"""The RFC 6962 tree, checked against Certificate Transparency's published vectors."""

import hashlib
import itertools

import pytest

from app.modules.deal_memo import merkle

# The leaves and roots used by Certificate Transparency's own test suites
# (merkletree tests in google/certificate-transparency and trillian).
LEAVES = [
    bytes.fromhex(h)
    for h in (
        "",
        "00",
        "10",
        "2021",
        "3031",
        "40414243",
        "5051525354555657",
        "606162636465666768696a6b6c6d6e6f",
    )
]
ROOTS = {
    1: "6e340b9cffb37a989ca544e6bb780a2c78901d3fb33738768511a30617afa01d",
    2: "fac54203e7cc696cf0dfcb42c92a1d9dbaf70ad9e621f4bd8d98662f00e3c125",
    3: "aeb6bcfe274b70a14fb067a5e5578264db0fa9b51af5e0ba159158f329e06e77",
    4: "d37ee418976dd95753c1c73862b9398fa2a2cf9b4ff0fdfe8b30cd95209614b7",
    5: "4e3bbb1f7b478dcfe71fb631631519a3bca12c9aefca1612bfce4c13a86264d4",
    6: "76e67dadbcdf1e10e1b74ddc608abd2f98dfb16fbce75277b5232a127f2087ef",
    7: "ddb89be403809e325750d3d263cd78929c2942b7942a34b77e122c9594a74c8c",
    8: "5dc9da79a70659a9ad559cb701ded9a2ab9d823aad2f4960cfe370eff4604328",
}


@pytest.mark.parametrize("size", sorted(ROOTS))
def test_roots_match_certificate_transparencys_vectors(size):
    assert merkle.root(LEAVES[:size]).hex() == ROOTS[size]


def test_the_empty_tree_is_the_hash_of_nothing():
    assert merkle.root([]) == hashlib.sha256(b"").digest()


@pytest.mark.parametrize("size", range(1, 18))
def test_every_leaf_proves_its_way_back_to_the_root(size):
    leaves = [bytes([i]) * 48 for i in range(size)]
    expected = merkle.root(leaves)

    for index in range(size):
        path = merkle.audit_path(index, leaves)
        assert merkle.root_from_path(index, size, leaves[index], path) == expected


@pytest.mark.parametrize("size", [2, 5, 8, 13])
def test_a_proof_for_one_leaf_does_not_prove_another(size):
    leaves = [bytes([i]) * 48 for i in range(size)]
    expected = merkle.root(leaves)

    for index, other in itertools.permutations(range(size), 2):
        path = merkle.audit_path(index, leaves)
        assert merkle.root_from_path(index, size, leaves[other], path) != expected


def test_a_changed_leaf_changes_the_root():
    leaves = [bytes([i]) * 48 for i in range(6)]
    changed = [*leaves[:3], b"\xff" * 48, *leaves[4:]]

    assert merkle.root(changed) != merkle.root(leaves)


def test_a_leaf_cannot_pose_as_an_inner_node():
    """The 0x00 / 0x01 prefixes: two leaves' hashes joined are not one leaf."""
    a, b = b"a", b"b"
    forged = merkle.leaf_hash(a) + merkle.leaf_hash(b)

    assert merkle.root([forged]) != merkle.root([a, b])


@pytest.mark.parametrize(
    ("index", "size", "path_change"),
    [(0, 4, "shorter"), (0, 4, "longer"), (4, 4, "none")],
)
def test_malformed_proofs_are_refused(index, size, path_change):
    leaves = [bytes([i]) for i in range(4)]
    path = merkle.audit_path(0, leaves)
    if path_change == "shorter":
        path = path[:-1]
    elif path_change == "longer":
        path = [*path, b"\x00" * 32]

    with pytest.raises(ValueError):
        merkle.root_from_path(index, size, leaves[0], path)


def test_asking_for_a_leaf_that_is_not_there_is_an_error():
    with pytest.raises(IndexError):
        merkle.audit_path(3, [b"a", b"b"])
