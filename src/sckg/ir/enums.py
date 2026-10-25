from __future__ import annotations

from enum import StrEnum


class Language(StrEnum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    C = "c"
    CPP = "cpp"
    JAVA = "java"
    GO = "go"
    UNKNOWN = "unknown"
    PROTOBUF = "protobuf"
    CSHARP = "csharp"


class SymbolKind(StrEnum):
    REPOSITORY = "repository"
    PACKAGE = "package"
    MODULE = "module"
    FILE = "file"
    CLASS = "class"
    INTERFACE = "interface"
    FUNCTION = "function"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    VARIABLE = "variable"
    PARAMETER = "parameter"
    FIELD = "field"
    TYPE = "type"
    IMPORT = "import"
    CODE_CHUNK = "code_chunk"
    COMMIT = "commit"


class RelationType(StrEnum):
    CONTAINS = "CONTAINS"
    DEFINES = "DEFINES"
    REFERENCES = "REFERENCES"
    CALLS = "CALLS"
    IMPORTS = "IMPORTS"
    INHERITS = "INHERITS"
    IMPLEMENTS = "IMPLEMENTS"
    OVERRIDES = "OVERRIDES"
    HAS_TYPE = "HAS_TYPE"
    PASSES_ARG = "PASSES_ARG"
    RETURNS = "RETURNS"
    FLOWS_TO = "FLOWS_TO"
    MUTATES = "MUTATES"
    USES = "USES"
    EXTENDS = "EXTENDS"
    POLYMORPHIC_CALL = "POLYMORPHIC_CALL"
    HTTP_CALLS = "HTTP_CALLS"
    CONSUMES = "CONSUMES"
    DEFINES_RPC = "DEFINES_RPC"
    SEMANTIC_SIMILAR = "SEMANTIC_SIMILAR"
    TOUCHES = "TOUCHES"


class Provenance(StrEnum):
    TREE_SITTER = "TREE_SITTER"
    AST = "AST"
    IMPORT_RESOLVER = "IMPORT_RESOLVER"
    TYPE_RESOLVER = "TYPE_RESOLVER"
    STATIC_ANALYSIS = "STATIC_ANALYSIS"
    HEURISTIC = "HEURISTIC"
    USER_SUPPLIED = "USER_SUPPLIED"
