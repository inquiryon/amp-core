"""Architecture enforcement (OSS-002): the public core must not import
Enterprise modules, web frameworks, databases, or SaaS infrastructure."""

import ast
import os

SRC = os.path.join(os.path.dirname(__file__), '..', 'src', 'amp_core')

FORBIDDEN_PREFIXES = (
    'flask', 'mysql', 'sqlalchemy', 'alembic', 'requests', 'stripe',
    'opensearch', 'resend', 'rlhf', 'amp_rlhf', 'inquiryon_amp_backend',
    'agent_hitl', 'boto3', 'redis', 'celery',
)


def iter_imports():
    for dirpath, _dirnames, filenames in os.walk(os.path.abspath(SRC)):
        for name in filenames:
            if not name.endswith('.py'):
                continue
            path = os.path.join(dirpath, name)
            with open(path, encoding='utf-8') as f:
                tree = ast.parse(f.read(), filename=path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        yield path, alias.name
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    yield path, node.module or ''


def test_no_forbidden_imports():
    violations = [
        f'{path}: {module}'
        for path, module in iter_imports()
        if any(module == p or module.startswith(p + '.') for p in FORBIDDEN_PREFIXES)
    ]
    assert violations == []


def test_core_has_no_runtime_dependencies():
    # pyproject dependencies must stay empty — adapters live in other packages.
    import tomllib
    with open(os.path.join(SRC, '..', '..', 'pyproject.toml'), 'rb') as f:
        pyproject = tomllib.load(f)
    assert pyproject['project']['dependencies'] == []
