import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import textwrap
import unittest


class TexturePathTests(unittest.TestCase):
    def check_changes(self, changes, mode='100644'):
        workflow = (Path(__file__).resolve().parents[1]/'.github/workflows/validate.yml').read_text(encoding='utf-8')
        step = workflow.split('      - name: "Check path restrictions"', 1)[1].split('      - name:', 1)[0]
        script = textwrap.dedent(step.split('        run: |\n', 1)[1])
        bash = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash')
        self.assertTrue(bash)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root/'repo'
            repo.mkdir()
            env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)

            def git(*args):
                return subprocess.check_output(['git', *args], cwd=repo, env=env, stderr=subprocess.PIPE).decode().strip()

            git('init', '-q')
            git('config', 'user.name', 'Path test')
            git('config', 'user.email', 'test@example.invalid')
            git('config', 'core.autocrlf', 'false')
            for index, (old, _) in enumerate(changes):
                path = repo/old
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((f'fixture {index}\n'*100).encode())
            git('add', '.')
            git('commit', '-qm', 'before')
            base = git('rev-parse', 'HEAD')
            for old, new in changes:
                content = (repo/old).read_bytes()
                (repo/old).unlink()
                path = repo/new
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            git('add', '-A')
            if mode != '100644':
                for _, new in changes:
                    blob = git('ls-files', '--stage', '--', new).split()[1]
                    git('update-index', '--cacheinfo', mode, blob, new)
            git('commit', '-qm', 'after')
            head = git('rev-parse', 'HEAD')
            script_path = root/'check.sh'
            script_path.write_bytes(script.encode())
            result = subprocess.run([bash, script_path.as_posix()], cwd=repo,
                                    env=dict(env, BASE_SHA=base, HEAD_SHA=head), capture_output=True, text=True)
            report = repo/'path-report.md'
            return result, report.read_text(encoding='utf-8') if report.exists() else ''

    def test_sparse_texture_pairs_pass(self):
        pairs = [
            ('ui/icon/120000/en/120411_hr1.tex', 'ui/icon/120000/en/120459_hr1.tex'),
            ('ui/icon/127000/en/127122.tex', 'ui/icon/121000/en/121614_hr1.tex'),
            ('ui/icon/120000/en/120411.tex', 'ui/icon/128000/en/128529_hr1.tex'),
            ('ui/icon/127000/en/127122_hr1.tex', 'ui/icon/128000/en/128533.tex'),
        ]
        result, report = self.check_changes(pairs)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('satisfy', report)

    def test_unrelated_and_non_english_renames_stay_blocked(self):
        for old, new in [
            ('corpus/flat/A.json', 'corpus/flat/B.json'),
            ('corpus/flat/A.json', 'ui/icon/120000/en/120001.tex'),
            ('ui/icon/120000/en/120001.tex', 'ui/icon/120000/fr/120001.tex'),
        ]:
            with self.subTest(old=old, new=new):
                result, report = self.check_changes([(old, new)])
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('Renamed or copied path', report)

    def test_executable_and_symlink_textures_stay_blocked(self):
        pair = [('ui/icon/120000/en/120001.tex', 'ui/icon/120000/en/120002.tex')]
        for mode in ['100755', '120000']:
            with self.subTest(mode=mode):
                result, report = self.check_changes(pair, mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn('Data must be a regular non-executable file', report)

    def test_existing_glossary_migration_still_passes(self):
        result, report = self.check_changes([
            ('glossary/bnpc-override.json', 'glossary/bnpc-canonical-names.json')])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('satisfy', report)


if __name__ == '__main__':
    unittest.main()
