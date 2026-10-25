The builder, polyglot parser, workspace composer, and lineage layer in this directory are adapted
from SNK0-0/SCKG_Build (MIT, as declared in its pyproject.toml), fetched on
2026-10-02 at commit 2d6d6765547e485b1c93d957130cedc93b676cd8.
Original repository: https://github.com/SNK0-0/SCKG_Build .
Imports were changed to package-relative paths. The adapter.py module is local to
this project and translates the layered MultiDiGraph into LNIR for EG-POT.
