"""Portable whitespace normalization with stable PostgreSQL index reflection."""
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy import String


class Trimmed(FunctionElement):
    type = String()
    inherit_cache = True


@compiles(Trimmed)
def compile_trimmed(element, compiler, **kwargs):
    return 'trim(' + compiler.process(element.clauses, **kwargs) + ')'


@compiles(Trimmed, 'postgresql')
def compile_trimmed_postgres(element, compiler, **kwargs):
    return 'btrim(' + compiler.process(element.clauses, **kwargs) + ')'
