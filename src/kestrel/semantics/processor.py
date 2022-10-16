import logging
import pathlib
import datetime
import re

from kestrel.syntax.parser import get_all_input_var_names
from kestrel.syntax.reference import deref_and_flatten_value_to_list
from kestrel.symboltable.symtable import SymbolTable
from firepit.sqlstorage import SqlStorage
from kestrel.datasource.manager import DataSourceManager

from kestrel.exceptions import (
    InvalidAttribute,
    VariableNotExist,
    UnsupportedRelation,
    KestrelInternalError,
)
from kestrel.codegen.relations import stix_2_0_ref_mapping, generic_relations
from kestrel.semantics.reference import make_deref_func, make_var_timerange_func

_logger = logging.getLogger(__name__)


def semantics_processing(
    stmt: dict,
    symtable: SymbolTable,
    store: SqlStorage,
    data_source_manager: DataSourceManager,
    config: dict,
):
    # semantics checking and completion

    _check_elements_not_empty(stmt)

    for input_var_name in get_all_input_var_names(stmt):
        _check_var_exists(input_var_name, symtable)

    if stmt["command"] == "get":
        _process_datasource_in_get(stmt, symtable, data_source_manager)

    if stmt["command"] == "load" or stmt["command"] == "save":
        stmt["path"] = pathlib.Path(stmt["path"]).expanduser().resolve()

    if stmt["command"] == "find":
        _check_semantics_on_find(stmt, symtable[stmt["input"]].type)

    if "attrs" in stmt:
        var_struct = symtable[stmt["input"]]
        stmt["attrs"] = _normalize_attrs(stmt, var_struct)

    deref_func = make_deref_func(store, symtable)
    get_timerange_func = make_var_timerange_func(store, symtable)

    if "where" in stmt:
        stmt["where"].deref(deref_func, get_timerange_func)

        if stmt["command"] == "get":
            center_entity_type = stmt["type"]
        elif stmt["command"] in ("find", "assign", "disp"):
            center_entity_type = symtable[stmt["input"]].type

        stmt["where"].add_center_entity(center_entity_type)

        if stmt["command"] in ("assign", "disp"):
            stmt["where"] = stmt["where"].to_firepit()
        elif stmt["command"] in ("get", "find"):
            time_adj = (
                config["stixquery"]["timerange_start_offset"],
                config["stixquery"]["timerange_stop_offset"],
            )
            stmt["patternbody"] = stmt["where"].to_stix()

    if "arguments" in stmt:
        stmt["arguments"] = {
            k: _arguments_deref(v, deref_func, get_timerange_func)
            for k, v in stmt["arguments"].items()
        }


def _check_elements_not_empty(stmt):
    for k, v in stmt.items():
        if isinstance(v, str) and not v:
            raise KestrelInternalError(f'incomplete parser; empty value for "{k}"')


def _check_var_exists(var_name, symtable):
    if var_name not in symtable:
        raise VariableNotExist(var_name)


def _normalize_attrs(stmt, v):
    props = []
    for attr in re.split(r",\s*", stmt["attrs"]):
        entity_type, _, prop = attr.rpartition(":")
        if entity_type and entity_type != v.type:
            raise InvalidAttribute(attr)
        props.append(prop)
    return ",".join(props)


def _process_datasource_in_get(stmt, symtable, data_source_manager):

    if stmt["command"] != "get":
        return

    # parser doesn't understand whether a data source is a Kestrel var
    # this function differente a Kestrel variable source from a data source
    if "datasource" in stmt:
        source = stmt["datasource"]
        if source in symtable:
            stmt["variablesource"] = source
            del stmt["datasource"]

    # complete default data source
    last_ds = data_source_manager.queried_data_sources[-1]
    if "variablesource" not in stmt and "datasource" not in stmt:
        if ds:
            stmt["datasource"] = ds


def _check_semantics_on_find(stmt, input_type):

    if stmt["command"] != "find":
        return

    # relation should be in lowercase after parsing by kestrel.syntax.parser
    relation = stmt["relation"]
    return_type = stmt["type"]

    (entity_x, entity_y) = (
        (input_type, return_type) if stmt["reversed"] else (return_type, input_type)
    )

    if (
        entity_x,
        relation,
        entity_y,
    ) not in stix_2_0_ref_mapping and relation not in generic_relations:
        raise UnsupportedRelation(entity_x, relation, entity_y)


def _arguments_deref(v, deref_func, get_timerange_func):
    # not bother timerange for arguments deref
    w, _ = deref_and_flatten_value_to_list(v, deref_func, get_timerange_func)
    if len(w) == 1:
        w = w[0]
    return w