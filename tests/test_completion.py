import os
import pytest
from kestrel.codegen.relations import all_relations
from kestrel.session import Session
from kestrel.syntax.utils import (
    LITERALS,
    AGG_FUNCS,
    TRANSFORMS,
)


KNOWN_ETYPES = {
    "artifact",
    "autonomous-system",
    "directory",
    "domain-name",
    "email-addr",
    "email-message",
    "file",
    "ipv4-addr",
    "ipv6-addr",
    "mac-addr",
    "mutex",
    "network-traffic",
    "process",
    "software",
    "url",
    "user-account",
    "windows-registry-key",
    "x-ibm-finding",
    "x-oca-asset",
    "x-oca-event",
}


@pytest.fixture
def a_session():
    cwd = os.path.dirname(os.path.abspath(__file__))
    bundle = os.path.join(cwd, "test_bundle.json")
    session = Session(debug_mode=True)
    stmt = (
        "conns = get network-traffic"
        f" from file://{bundle}"
        " where [network-traffic:dst_port < 10000]"
    )
    session.execute(stmt)
    return session


@pytest.mark.parametrize(
    "code, expected",
    [
        ("x", []),  # No suggestions
        ("x ", {"=", "+"}),
        ("c", {"onns"}),
        ("conns", [""]),  # Empty string means word is complete
        ("conns ", {"=", "+"}),
        ("disp ", {"conns", "_"} | TRANSFORMS),
        (
            "procs = ",
            {"GET", "FIND", "JOIN", "SORT", "GROUP", "LOAD", "NEW", "conns", "_"}
            | TRANSFORMS,
        ),
        ("procs = G", {"ET", "ROUP"}),
        ("procs = F", {"IND"}),
        ("procs = FI", {"ND"}),
        ("procs = FIN", {"D"}),
        ("procs = FIND", []),
        ("procs = FIND ", KNOWN_ETYPES),
        ("procs = FIND p", ["rocess"]),
        ("procs = FIND process", [""]),
        # ("procs = FIND process ", {"created", "loaded", "linked"}),
        ("procs = FIND process ", all_relations),
        ("procs = FIND process l", {"oaded", "inked"}),
        ("procs = FIND process c", {"reated", "ontained"}),
        ("procs = FIND process created ", {"conns", "_", "BY"}),
        ("procs = FIND process created BY ", {"conns", "_"}),
        ("procs2 = SORT procs ", {"BY"}),
        ("grps = GR", {"OUP"}),
        ("grps = GROUP ", {"conns", "_"}),
        ("grps = GROUP conns ", {"BY"}),
        ("grps = GROUP conns by ", {"ATTRIBUTE", "BIN"}),  # TODO: we don't suggest attrs yet
        ("urls = g", ["et", "roup"]),
        ("urls = ge", ["t"]),
        ("urls = get ", KNOWN_ETYPES),
        ("urls = get url ", ["FROM", "WHERE"]),
        (
            "urls = get url from ",
            ["_", "conns", "file://", "http://", "https://", "stixshifter://"],
        ),
        ("urls = get url where ", {'ENTITY_ATTRIBUTE_PATH', 'LSQB', 'LPAR'}),
        ("DISP conns ATTR d", {"dst_port", "dst_ref.id", "dst_ref.value"}),
        ("DISP conns ATTR s", {"src_port", "src_ref.id", "src_ref.value"}),
        ("DISP conns ATTR ", {
            "dst_port",
            "dst_ref.id",
            "dst_ref.value",
            "end",
            "id",
            "protocols",
            "src_port",
            "src_ref.id",
            "src_ref.value",
            "start",
        }),
    ],
)
def test_do_complete_after_get(a_session, code, expected):
    result = a_session.do_complete(code, len(code))
    assert set(result) == set(expected)
