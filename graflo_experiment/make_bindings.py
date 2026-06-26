"""Runtime Graflo bindings for the APM CSV files."""

from __future__ import annotations

from pathlib import Path

from apm_mapping import TABLE_ALIASES
from generate_manifest import resource_bindings_by_table, source_tables


def make_bindings(data_dir: str | Path = "data/mock"):
    try:
        from graflo import Bindings
        from graflo.architecture.contract.bindings import FileConnector
    except ImportError as exc:
        raise RuntimeError(
            "GraFlo is not installed. Install it with `python3 -m pip install graflo`."
        ) from exc

    bindings = Bindings()
    connectors_by_table = {}
    for table_name in sorted(source_tables()):
        connector_name = f"{table_name}_csv"
        aliases = TABLE_ALIASES.get(table_name, [table_name])
        regex = "^(" + "|".join(aliases) + ")\\.csv$"
        connector = make_file_connector(FileConnector, connector_name, regex, data_dir)
        bindings.add_connector(connector)
        connectors_by_table[table_name] = connector

    for table_name, resource_names in resource_bindings_by_table().items():
        connector = connectors_by_table[table_name]
        for resource_name in resource_names:
            bindings.bind_resource(resource_name, connector)

    return bindings


def make_file_connector(file_connector_cls, name: str, regex: str, data_dir: str | Path):
    try:
        return file_connector_cls(
            name=name,
            regex=regex,
            sub_path=Path(data_dir),
        )
    except Exception as exc:
        message = str(exc)
        if "sub_path" not in message and "extra_forbidden" not in message and "Extra inputs" not in message:
            raise
        return file_connector_cls(
            name=name,
            regex=regex,
        )
