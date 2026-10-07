"""Regression checks using a disposable PostgreSQL cluster, never the app DB.

Run this file directly with Python. Requires local PostgreSQL binaries.
No .env, application settings, network DB URL or third-party Python packages.
"""
import ast
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PG_BIN = Path(os.environ.get('TEST_PG_BIN', r'C:\Program Files\PostgreSQL\16\bin'))


def migration_source(name):
    return ast.parse((ROOT / 'alembic' / 'versions' / name).read_text(encoding='utf-8'))


def normalization_sql():
    tree = migration_source('021a_saneamiento_historial.py')
    upgrade = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'upgrade')
    statements = [node.value.args[0].value for node in upgrade.body
                  if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
                  and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'execute'
                  and node.value.args and isinstance(node.value.args[0], ast.Constant)]
    return next(sql for sql in statements if "IN ('string','number','object')" in sql)


def wheel_check():
    tree = migration_source('022_integridad_bd.py')
    constants = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            if node.targets[0].id == 'NEUMATICO_UNICO':
                constants['NEUMATICO_UNICO'] = ast.literal_eval(node.value)
            if node.targets[0].id == 'CHECKS':
                for entry in node.value.elts:
                    if ast.literal_eval(entry.elts[1]) == 'ck_neumaticos_rueda_unica':
                        expression = entry.elts[2]
                        return constants[expression.id] if isinstance(expression, ast.Name) else ast.literal_eval(expression)
    raise AssertionError('Wheel constraint not found')


@unittest.skipUnless((PG_BIN / 'initdb.exe').is_file(), 'Local PostgreSQL binaries required; set TEST_PG_BIN')
class JsonCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='narbus-jsonb-test-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.data = Path(cls.temp.name) / 'data'
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        cls.run_command('initdb.exe', '-D', str(cls.data), '-U', 'migration_test',
                        '--auth=trust', '--no-locale', '--encoding=UTF8')
        cls.run_command('pg_ctl.exe', '-D', str(cls.data), '-l', str(Path(cls.temp.name) / 'postgres.log'),
                        '-o', f'-h 127.0.0.1 -p {cls.port} -c fsync=off', '-w', 'start')
        cls.addClassCleanup(cls.stop)

    @classmethod
    def run_command(cls, binary, *args, input=None):
        env = os.environ.copy()
        # Remove libpq environment settings; this harness always uses its own cluster.
        for key in list(env):
            if key.upper().startswith('PG'):
                env.pop(key)
        # A pg_ctl child can inherit pipe handles on Windows and prevent communicate
        # from returning even after startup. File output avoids inherited pipe waits.
        with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as output:
            result = subprocess.run([str(PG_BIN / binary), *args], input=input, text=True,
                                    stdout=output, stderr=output, timeout=45, env=env,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            output.seek(0)
            content = output.read().strip()
        if result.returncode:
            raise AssertionError(content)
        return content

    @classmethod
    def stop(cls):
        cls.run_command('pg_ctl.exe', '-D', str(cls.data), '-m', 'fast', '-w', 'stop')

    def sql(self, query):
        return self.run_command('psql.exe', '-X', '-qAt', '-v', 'ON_ERROR_STOP=1',
                                '-h', '127.0.0.1', '-p', str(self.port), '-U', 'migration_test',
                                '-d', 'postgres', input=query)

    def check_normalization(self, kind):
        result = self.sql(f"""
            BEGIN;
            CREATE TEMP TABLE reportes_neumaticos(id int, ruedas {kind}, ruedas_originales json);
            INSERT INTO reportes_neumaticos VALUES
              (1, '\"Rueda 4\"', NULL), (2, '4', NULL), (3, '{{\"posicion\":\"1D\",\"presion\":110}}', NULL),
              (4, '[\"Rueda 4\"]', NULL), (5, '[\"1D\",\"1I\"]', NULL), (6, '[]', NULL),
              (7, 'true', NULL), (8, 'null', NULL), (9, NULL, NULL);
            {normalization_sql()};
            SELECT count(*) FROM reportes_neumaticos WHERE id <= 3
              AND jsonb_typeof(ruedas::jsonb) = 'array'
              AND jsonb_array_length(ruedas::jsonb) = 1
              AND ruedas::jsonb->0 = ruedas_originales::jsonb;
            SELECT count(*) FROM reportes_neumaticos WHERE id >= 4 AND ruedas_originales IS NULL;
            SELECT jsonb_typeof(ruedas::jsonb) FROM reportes_neumaticos WHERE id=5;
            SELECT jsonb_array_length(ruedas::jsonb) FROM reportes_neumaticos WHERE id=5;
            ROLLBACK;
        """)
        self.assertEqual(result.splitlines(), ['3', '6', 'array', '2'])

    def check_validation(self, kind):
        result = self.sql(f"""
            BEGIN;
            CREATE TEMP TABLE reportes_neumaticos(id int, ruedas {kind});
            INSERT INTO reportes_neumaticos VALUES
              (1, '[\"1D\"]'), (2, '[{{\"posicion\":\"1D\"}}]'), (3, '[]'),
              (4, '[\"1D\",\"1I\"]'), (5, '{{\"posicion\":\"1D\"}}'), (6, '\"1D\"'),
              (7, '7'), (8, 'true'), (9, 'null'), (10, NULL);
            SELECT id FROM reportes_neumaticos WHERE ({wheel_check()}) IS FALSE ORDER BY id;
            ROLLBACK;
        """)
        self.assertEqual(result.splitlines(), [str(i) for i in range(3, 11)])

    def check_constraint(self, kind):
        result = self.sql(f"""
            BEGIN;
            CREATE TEMP TABLE reportes_neumaticos(ruedas {kind} NOT NULL,
              CONSTRAINT ck_neumaticos_rueda_unica CHECK ({wheel_check()}));
            INSERT INTO reportes_neumaticos VALUES ('[\"1D\"]'), ('[{{\"posicion\":\"1I\"}}]');
            DO $test$
            DECLARE payload text;
            BEGIN
              FOREACH payload IN ARRAY ARRAY['[]','[\"1D\",\"1I\"]','{{\"posicion\":\"1D\"}}','\"1D\"','7','true','null'] LOOP
                BEGIN
                  EXECUTE format('INSERT INTO reportes_neumaticos VALUES (%L)', payload);
                  RAISE EXCEPTION 'Invalid payload accepted: %', payload;
                EXCEPTION WHEN check_violation THEN NULL;
                END;
              END LOOP;
            END $test$;
            SELECT count(*) FROM reportes_neumaticos;
            ROLLBACK;
        """)
        self.assertEqual(result, '2')

    def test_normalization_json(self): self.check_normalization('json')
    def test_normalization_jsonb(self): self.check_normalization('jsonb')
    def test_preflight_json(self): self.check_validation('json')
    def test_preflight_jsonb(self): self.check_validation('jsonb')
    def test_constraint_json(self): self.check_constraint('json')
    def test_constraint_jsonb(self): self.check_constraint('jsonb')

    def test_audit_uses_the_constraint_expression(self):
        tree = migration_source('022_integridad_bd.py')
        audit = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'audit')
        # An override would allow the preflight to pass but fail when creating the CHECK.
        self.assertNotIn("ck_neumaticos_rueda_unica", ast.unparse(audit))


if __name__ == '__main__':
    unittest.main(verbosity=2)
