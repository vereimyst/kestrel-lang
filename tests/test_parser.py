import re

from lark import UnexpectedToken
import pytest

from kestrel.syntax.parser import parse_kestrel
from kestrel.syntax.ecgpattern import Reference
from kestrel.exceptions import InvalidECGPattern
from firepit.timestamp import timefmt


@pytest.mark.parametrize("pattern",
    ["[url:value LIKE '%']"
    ,"url:value LIKE '%'"
    ,"value LIKE '%'"
    ,"[value LIKE '%']"
    ,"[url:value \n LIKE '%']"
    ,"value LIKE \n '%'"
    ],
)
def test_simple_get(pattern):
    results = parse_kestrel(f"y = get url from udi://all where {pattern}")
    result = results[0]

    assert result["command"] == "get"
    assert result["type"] == "url"
    assert result["datasource"] == "udi://all"

    where = results[0]["where"]
    where.add_center_entity("url")
    assert where.to_stix(None, None) == "[url:value LIKE '%']"


@pytest.mark.parametrize("pattern",
    ["pid IN (1, 2, 3)"
    ,"[pid IN (1, 2, 3)]"
    ,"[process:pid IN (1, 2, 3)]"
    ],
)
def test_assign_in(pattern):
    results = parse_kestrel(f"y = x WHERE {pattern}")
    where = results[0]["where"]
    where.add_center_entity("process")
    assert where.to_stix(None, None) == "[process:pid IN (1,2,3)]"


@pytest.mark.parametrize(
    "pattern, errprint",
    [
        ("pid = (1, 2, 3)", 'a list should be paired with the operator "IN"'),
        ("pid IN 'asdf'", 'inappropriately pair operator "IN" with literal'),
    ],
)
def test_ecgp_in_exception(pattern, errprint):
    with pytest.raises(InvalidECGPattern) as einfo:
        results = parse_kestrel(f"y = x WHERE {pattern}")
    assert einfo.value.error == errprint


def test_quoted_datasource():
    results = parse_kestrel("y = get url from \"udi://My QRadar\" where [url:value LIKE '%']")
    result = results[0]
    assert result["command"] == "get"
    assert result["type"] == "url"
    assert result["datasource"] == "udi://My QRadar"

    where = results[0]["where"]
    where.add_center_entity("url")
    assert where.to_stix(None, None) == "[url:value LIKE '%']"


@pytest.mark.parametrize(
    "outvar, sco_type, ds, pat",
    [
        ("_my_var", "ipv4-addr", "something", "[ipv4-addr:value = '192.168.121.121']"),
        (
            "X1",
            "x-custom-object",
            "myscheme://foo.bar/whatever",
            "[x-other-custom-thing:x_custom_prop IN ('a','b','c')]",
        ),
        (
            "urls",
            "url",
            "file:///shared-vol/udsstx",
            "[url:value LIKE 'https://%'] START t'2021-03-29T19:25:12.345Z' STOP t'2021-03-29T19:30:12.345Z'",
        ),
        (
            "ext_dns_conns",
            "network-traffic",
            '"udi://10k Traffic"',
            "[(network-traffic:dst_port = 53 AND network-traffic:dst_ref.value NOT ISSUBSET '192.168.1.0/24')]",
        ),
    ],
)
def test_get(outvar, sco_type, ds, pat):
    results = parse_kestrel(f"{outvar} = GET {sco_type} FROM {ds} WHERE {pat}")
    result = results[0]
    assert result["output"] == outvar
    assert result["command"] == "get"
    assert result["type"] == sco_type
    assert result["datasource"] == ds.strip('"')  # We strip the double quotes

    where = results[0]["where"]
    where.add_center_entity("sco_type")
    assert where.to_stix(result["timerange"], None) == pat


def test_get_timerange():
    results = parse_kestrel("""
        x = GET process
            FROM xxx
            WHERE name = 'asdf'
            START 2022-10-18T01:02:03Z
            STOP  2022-10-19T04:05:06Z
        """)
    result = results[0]
    assert timefmt(result["timerange"][0]) == "2022-10-18T01:02:03.000Z"
    assert timefmt(result["timerange"][1]) == "2022-10-19T04:05:06.000Z"


def test_apply_params():
    results = parse_kestrel("apply xyz://my_analytic on foo with x=1, y=(a, b,c)")
    result = results[0]
    assert result["command"] == "apply"
    assert result["analytics_uri"] == "xyz://my_analytic"
    assert result["inputs"] == ["foo"]
    assert result["arguments"] == {"x": 1, "y": ["a", "b", "c"]}


def test_apply_params_with_dots():
    results = parse_kestrel("apply xyz://my_analytic on foo with x=0.1, y=a.value")
    result = results[0]
    assert result["command"] == "apply"
    assert result["analytics_uri"] == "xyz://my_analytic"
    assert result["inputs"] == ["foo"]
    assert result["arguments"] == {"x": 0.1, "y": Reference("a", "value")}


def test_apply_params_with_at():
    results = parse_kestrel("apply xyz://my_analytic on foo with x=\"https://www.xyz.com/123@me.com/action\"")
    result = results[0]
    assert result["command"] == "apply"
    assert result["analytics_uri"] == "xyz://my_analytic"
    assert result["inputs"] == ["foo"]
    assert result["arguments"] == {"x": "https://www.xyz.com/123@me.com/action"}


def test_apply_params_with_decimal_and_dots():
    results = parse_kestrel("apply xyz://my_analytic on foo with x=0.1, y=[a.value ,b,c]")
    result = results[0]
    assert result["command"] == "apply"
    assert result["analytics_uri"] == "xyz://my_analytic"
    assert result["inputs"] == ["foo"]
    assert result["arguments"] == {"x": 0.1, "y": [Reference("a", "value"), "b", "c"]}


def test_apply_params_no_equals():
    with pytest.raises(UnexpectedToken):
        parse_kestrel("apply xyz://my_analytic on foo with x=1, y")


def test_grouping_0():
    results = parse_kestrel("y = group x by foo")
    result = results[0]
    print(result)
    assert result["command"] == "group"
    assert result["input"] == "x"
    assert result["attributes"] == ["foo"]
    assert "aggregations" not in result


def test_grouping_1():
    results = parse_kestrel("y = group x by foo with sum(baz)")
    result = results[0]
    print(result)
    assert result["command"] == "group"
    assert result["input"] == "x"
    assert result["attributes"] == ["foo"]
    assert result["aggregations"] == [
        {"attr": "baz", "func": "sum", "alias": "sum_baz"},
    ]


def test_grouping_2():
    results = parse_kestrel("y = group x BY foo, bar WITH MAX(baz) AS biggest, MIN(blah)")
    result = results[0]
    print(result)
    assert result["command"] == "group"
    assert result["input"] == "x"
    assert result["attributes"] == ["foo", "bar"]
    assert result["aggregations"] == [
        {"attr": "baz", "func": "max", "alias": "biggest"},
        {"attr": "blah", "func": "min", "alias": "min_blah"},
    ]


def test_grouping_3():
    results = parse_kestrel(
        "y = group x by foo with avg(bar), count(baz), max(blah) as whatever"
    )
    result = results[0]
    print(result)
    assert result["command"] == "group"
    assert result["input"] == "x"
    assert result["attributes"] == ["foo"]
    assert result["aggregations"] == [
        {"attr": "bar", "func": "avg", "alias": "avg_bar"},
        {"attr": "baz", "func": "count", "alias": "count_baz"},
        {"attr": "blah", "func": "max", "alias": "whatever"},
    ]
