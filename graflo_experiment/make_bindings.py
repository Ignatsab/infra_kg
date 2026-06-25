"""Runtime Graflo bindings for the APM CSV files."""

from __future__ import annotations

from pathlib import Path

from apm_mapping import TABLE_ALIASES
from generate_manifest import resources_by_table


def make_bindings(data_dir: str | Path = "data/mock"):
    try:
        from graflo import Bindings
        from graflo.architecture.contract.bindings import FileConnector
    except ImportError as exc:
        raise RuntimeError(
            "GraFlo is not installed. Install it with `python3 -m pip install graflo`."
        ) from exc

    connectors = []
    resource_connector = {}
    for table_name in sorted(resources_by_table()):
        connector_name = f"{table_name}_csv"
        aliases = TABLE_ALIASES.get(table_name, [table_name])
        regex = "^(" + "|".join(aliases) + ")\\.csv$"
        connectors.append(
            FileConnector(
                name=connector_name,
                regex=regex,
                sub_path=Path(data_dir),
            )
        )
        resource_connector[table_name] = connector_name

    return Bindings(
        connectors=connectors,
        resource_connector=resource_connector,
    )
