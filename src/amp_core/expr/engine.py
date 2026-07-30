"""Constrained boolean-formula engine for AMP policy criteria.

Replaces the monolith's ``eval()``-based formula evaluation (OSS-003 task 3).
Formulas are parsed with :mod:`ast` and interpreted directly — no Python
bytecode is ever executed for user-supplied input.

Language surface (v0), chosen to cover the characterized formula corpus:

- literals: str, int, float, bool, None; lists and tuples
- names resolved from the parameter environment (missing names raise
  :class:`FormulaNameError`, which callers translate to the criterion's
  fallback result — hard criteria fail closed)
- boolean ops ``and``/``or``/``not``; comparisons including ``in``/``not in``
- arithmetic ``+ - * / // %`` and unary ``-``/``+``; ``**`` with small bounds
- conditional expressions ``x if c else y``
- generator expressions / list comprehensions with ``for`` and ``if`` parts
- calls to allow-listed builtins (``len any all str int float abs min max
  round``) and environment helpers (``lockdown``, ``get``)
- attribute access restricted to an allow-list of ``str`` methods plus
  ``dict.get`` — never on underscore names, never on other objects
- subscripts/slices on str/list/tuple/dict

Everything else (imports, lambdas, assignments, f-strings, starred args,
walrus, dunder access, arbitrary attributes/calls) is rejected at parse time
with :class:`FormulaSyntaxError`.

Resource limits: formula length, AST node count, an evaluation step budget,
comprehension iteration caps, and bounded ``**`` operands. Limit breaches
raise :class:`FormulaResourceError`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass


class FormulaError(Exception):
    """Base class for all formula failures."""


class FormulaSyntaxError(FormulaError):
    """Formula could not be parsed or uses a disallowed construct."""


class FormulaNameError(FormulaError):
    """Formula referenced a name absent from the environment."""


class FormulaResourceError(FormulaError):
    """Formula exceeded a resource limit."""


class FormulaRuntimeError(FormulaError):
    """Formula raised during interpretation (type errors etc.)."""


@dataclass(frozen=True)
class Limits:
    max_formula_chars: int = 2000
    max_ast_nodes: int = 500
    max_eval_steps: int = 100_000
    max_comprehension_iterations: int = 10_000
    max_pow_exponent: int = 32
    max_pow_base: float = 1e6


DEFAULT_LIMITS = Limits()

_ALLOWED_BUILTINS = {
    'len': len, 'any': any, 'all': all,
    'str': str, 'int': int, 'float': float,
    'abs': abs, 'min': min, 'max': max, 'round': round,
}

# Constant-like names the legacy engine accepted.
_CONST_NAMES = {'True': True, 'False': False, 'None': None,
                'true': True, 'false': False, 'null': None}

_ALLOWED_STR_METHODS = {
    'lower', 'upper', 'strip', 'lstrip', 'rstrip', 'startswith', 'endswith',
    'split', 'rsplit', 'replace', 'find', 'rfind', 'count', 'title',
    'casefold', 'isdigit', 'isalpha', 'isalnum', 'isspace', 'zfill',
}
_ALLOWED_DICT_METHODS = {'get', 'keys', 'values', 'items'}

_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.USub, ast.UAdd, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.FloorDiv, ast.Mod, ast.Pow, ast.Compare, ast.Eq, ast.NotEq, ast.Lt,
    ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.IfExp, ast.Call, ast.Attribute, ast.Subscript, ast.Slice, ast.Name,
    ast.Load, ast.Store, ast.Constant, ast.List, ast.Tuple, ast.Set, ast.Dict,
    ast.GeneratorExp, ast.ListComp, ast.SetComp, ast.comprehension,
    ast.keyword,
)


def parse_formula(formula: str, limits: Limits = DEFAULT_LIMITS) -> ast.Expression:
    """Parse and statically vet a formula. Raises FormulaSyntaxError/ResourceError."""
    if not isinstance(formula, str):
        raise FormulaSyntaxError('formula must be a string')
    if len(formula) > limits.max_formula_chars:
        raise FormulaResourceError('formula too long')
    try:
        tree = ast.parse(formula, mode='eval')
    except (SyntaxError, ValueError, MemoryError, RecursionError) as exc:
        raise FormulaSyntaxError(f'parse error: {exc}') from exc

    count = 0
    for node in ast.walk(tree):
        count += 1
        if count > limits.max_ast_nodes:
            raise FormulaResourceError('formula too complex')
        if not isinstance(node, _ALLOWED_NODES):
            raise FormulaSyntaxError(f'disallowed construct: {type(node).__name__}')
        if isinstance(node, ast.Attribute):
            if node.attr.startswith('_'):
                raise FormulaSyntaxError('underscore attributes are not allowed')
            if node.attr not in _ALLOWED_STR_METHODS | _ALLOWED_DICT_METHODS:
                raise FormulaSyntaxError(f'attribute not allowed: {node.attr}')
        if isinstance(node, ast.Name) and node.id.startswith('__'):
            raise FormulaSyntaxError('dunder names are not allowed')
        if isinstance(node, ast.keyword) and node.arg is None:
            raise FormulaSyntaxError('**kwargs is not allowed')
        if isinstance(node, ast.Call):
            if not isinstance(node.func, (ast.Name, ast.Attribute)):
                raise FormulaSyntaxError('only simple calls are allowed')
            if any(isinstance(a, ast.Starred) for a in node.args):
                raise FormulaSyntaxError('*args is not allowed')
    return tree


class _Interpreter:
    def __init__(self, env: dict, limits: Limits):
        self.env = env
        self.limits = limits
        self.steps = 0

    def _tick(self):
        self.steps += 1
        if self.steps > self.limits.max_eval_steps:
            raise FormulaResourceError('evaluation step budget exceeded')

    def eval(self, node):
        self._tick()
        method = getattr(self, f'_eval_{type(node).__name__}', None)
        if method is None:
            raise FormulaSyntaxError(f'disallowed construct: {type(node).__name__}')
        return method(node)

    def _eval_Expression(self, node):
        return self.eval(node.body)

    def _eval_Constant(self, node):
        return node.value

    def _eval_Name(self, node):
        if node.id in self.env:
            return self.env[node.id]
        if node.id in _CONST_NAMES:
            return _CONST_NAMES[node.id]
        if node.id in _ALLOWED_BUILTINS:
            return _ALLOWED_BUILTINS[node.id]
        raise FormulaNameError(f'unknown name: {node.id}')

    def _eval_List(self, node):
        return [self.eval(e) for e in node.elts]

    def _eval_Tuple(self, node):
        return tuple(self.eval(e) for e in node.elts)

    def _eval_Set(self, node):
        return {self.eval(e) for e in node.elts}

    def _eval_Dict(self, node):
        out = {}
        for k, v in zip(node.keys, node.values):
            if k is None:
                raise FormulaSyntaxError('dict unpacking is not allowed')
            out[self.eval(k)] = self.eval(v)
        return out

    def _eval_BoolOp(self, node):
        if isinstance(node.op, ast.And):
            result = True
            for v in node.values:
                result = self.eval(v)
                if not result:
                    return result
            return result
        result = False
        for v in node.values:
            result = self.eval(v)
            if result:
                return result
        return result

    def _eval_UnaryOp(self, node):
        val = self.eval(node.operand)
        try:
            if isinstance(node.op, ast.Not):
                return not val
            if isinstance(node.op, ast.USub):
                return -val
            if isinstance(node.op, ast.UAdd):
                return +val
        except Exception as exc:
            raise FormulaRuntimeError(str(exc)) from exc
        raise FormulaSyntaxError('disallowed unary operator')

    def _eval_BinOp(self, node):
        left = self.eval(node.left)
        right = self.eval(node.right)
        op = node.op
        try:
            if isinstance(op, ast.Pow):
                if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
                    raise FormulaRuntimeError('** requires numbers')
                if abs(right) > self.limits.max_pow_exponent or abs(left) > self.limits.max_pow_base:
                    raise FormulaResourceError('** operands out of bounds')
                return left ** right
            if isinstance(op, ast.Add):
                return left + right
            if isinstance(op, ast.Sub):
                return left - right
            if isinstance(op, ast.Mult):
                # Bound sequence repetition to keep memory in check.
                if isinstance(left, (str, list, tuple)) and isinstance(right, int) and right > 1000:
                    raise FormulaResourceError('sequence repetition too large')
                if isinstance(right, (str, list, tuple)) and isinstance(left, int) and left > 1000:
                    raise FormulaResourceError('sequence repetition too large')
                return left * right
            if isinstance(op, ast.Div):
                return left / right
            if isinstance(op, ast.FloorDiv):
                return left // right
            if isinstance(op, ast.Mod):
                return left % right
        except FormulaError:
            raise
        except Exception as exc:
            raise FormulaRuntimeError(str(exc)) from exc
        raise FormulaSyntaxError('disallowed binary operator')

    def _eval_Compare(self, node):
        left = self.eval(node.left)
        for op, comparator in zip(node.ops, node.comparators):
            right = self.eval(comparator)
            try:
                if isinstance(op, ast.Eq):
                    ok = left == right
                elif isinstance(op, ast.NotEq):
                    ok = left != right
                elif isinstance(op, ast.Lt):
                    ok = left < right
                elif isinstance(op, ast.LtE):
                    ok = left <= right
                elif isinstance(op, ast.Gt):
                    ok = left > right
                elif isinstance(op, ast.GtE):
                    ok = left >= right
                elif isinstance(op, ast.In):
                    ok = left in right
                elif isinstance(op, ast.NotIn):
                    ok = left not in right
                elif isinstance(op, ast.Is):
                    ok = left is right
                elif isinstance(op, ast.IsNot):
                    ok = left is not right
                else:
                    raise FormulaSyntaxError('disallowed comparison')
            except FormulaError:
                raise
            except Exception as exc:
                raise FormulaRuntimeError(str(exc)) from exc
            if not ok:
                return False
            left = right
        return True

    def _eval_IfExp(self, node):
        return self.eval(node.body) if self.eval(node.test) else self.eval(node.orelse)

    def _eval_Attribute(self, node):
        base = self.eval(node.value)
        attr = node.attr
        if isinstance(base, str) and attr in _ALLOWED_STR_METHODS:
            return getattr(base, attr)
        if isinstance(base, dict) and attr in _ALLOWED_DICT_METHODS:
            return getattr(base, attr)
        raise FormulaRuntimeError(
            f'attribute {attr!r} not allowed on {type(base).__name__}')

    def _eval_Subscript(self, node):
        base = self.eval(node.value)
        if not isinstance(base, (str, list, tuple, dict)):
            raise FormulaRuntimeError('subscript only allowed on str/list/tuple/dict')
        try:
            if isinstance(node.slice, ast.Slice):
                lower = self.eval(node.slice.lower) if node.slice.lower else None
                upper = self.eval(node.slice.upper) if node.slice.upper else None
                step = self.eval(node.slice.step) if node.slice.step else None
                return base[slice(lower, upper, step)]
            return base[self.eval(node.slice)]
        except FormulaError:
            raise
        except Exception as exc:
            raise FormulaRuntimeError(str(exc)) from exc

    def _eval_Call(self, node):
        func = self.eval(node.func)
        # Only environment helpers, allow-listed builtins, and allow-listed
        # bound methods survive parse + attribute vetting to reach this point.
        args = [self.eval(a) for a in node.args]
        kwargs = {}
        for kw in node.keywords:
            kwargs[kw.arg] = self.eval(kw.value)
        if not callable(func):
            raise FormulaRuntimeError('attempt to call a non-callable value')
        try:
            return func(*args, **kwargs)
        except FormulaError:
            raise
        except Exception as exc:
            raise FormulaRuntimeError(str(exc)) from exc

    def _iter_bounded(self, iterable):
        if isinstance(iterable, (str, list, tuple, set, dict, range)):
            items = list(iterable)
        else:
            raise FormulaRuntimeError('comprehension source must be a basic sequence')
        if len(items) > self.limits.max_comprehension_iterations:
            raise FormulaResourceError('comprehension too large')
        return items

    def _run_comprehension(self, generators, element_fn):
        results = []

        def rec(idx, env_overrides):
            if idx == len(generators):
                results.append(element_fn(env_overrides))
                return
            gen = generators[idx]
            if gen.is_async:
                raise FormulaSyntaxError('async comprehensions are not allowed')
            for item in self._iter_bounded(self._eval_with(gen.iter, env_overrides)):
                self._tick()
                bound = dict(env_overrides)
                self._bind_target(gen.target, item, bound)
                if all(self._eval_with(cond, bound) for cond in gen.ifs):
                    rec(idx + 1, bound)

        rec(0, {})
        return results

    def _bind_target(self, target, value, bound):
        if isinstance(target, ast.Name):
            bound[target.id] = value
        elif isinstance(target, ast.Tuple):
            try:
                values = list(value)
            except Exception as exc:
                raise FormulaRuntimeError('cannot unpack comprehension value') from exc
            if len(values) != len(target.elts):
                raise FormulaRuntimeError('comprehension unpack length mismatch')
            for t, v in zip(target.elts, values):
                self._bind_target(t, v, bound)
        else:
            raise FormulaSyntaxError('unsupported comprehension target')

    def _eval_with(self, node, overrides):
        saved = self.env
        self.env = {**saved, **overrides}
        try:
            return self.eval(node)
        finally:
            self.env = saved

    def _eval_GeneratorExp(self, node):
        return iter(self._run_comprehension(
            node.generators, lambda ov: self._eval_with(node.elt, ov)))

    def _eval_ListComp(self, node):
        return self._run_comprehension(
            node.generators, lambda ov: self._eval_with(node.elt, ov))

    def _eval_SetComp(self, node):
        return set(self._run_comprehension(
            node.generators, lambda ov: self._eval_with(node.elt, ov)))


def evaluate_formula(formula: str, env: dict,
                     limits: Limits = DEFAULT_LIMITS) -> bool:
    """Parse and interpret ``formula`` against ``env``; return its truthiness.

    Raises a :class:`FormulaError` subclass on any failure; callers decide the
    fallback semantics (hard criteria fail closed).
    """
    tree = parse_formula(formula, limits)
    result = _Interpreter(env, limits).eval(tree)
    return bool(result)
