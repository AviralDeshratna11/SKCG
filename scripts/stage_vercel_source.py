"""Export an authorized manual deployment without upstream Git identity or secrets."""
from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'site/graph-builder'
target = Path(tempfile.mkdtemp(prefix='egpot-vercel-'))
for pattern in ['*.py', '*.md']:
    for path in source.glob(pattern):
        shutil.copyfile(path, target / path.name)
for name in ['pyproject.toml', 'requirements.txt', 'vercel.json', '.vercelignore',
             'TRAVERSAL_CORE_PROVENANCE.json']:
    shutil.copyfile(source / name, target / name)
for name in ['api', 'sckg', 'viewer', 'bench/results']:
    shutil.copytree(source / name, target / name,
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
(target / '.vercel').mkdir()
shutil.copyfile(source / '.vercel/project.json', target / '.vercel/project.json')
provenance = {str(p.relative_to(target)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in target.rglob('*') if p.is_file() and '.vercel' not in p.parts}
(target / 'DEPLOYMENT_SOURCE_MANIFEST.json').write_text(json.dumps({
    'upstream': 'https://github.com/Vikas-Personal-Research-Org/Graph_Builder',
    'branch': subprocess.check_output(['git', '-C', str(source), 'branch', '--show-current'], text=True).strip(),
    'base_branch': 'shrey',
    'source_commit': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
    'deployment_type': 'manual source export; no inherited Git author identity',
    'files_sha256': provenance}, indent=2), encoding='utf-8')
(root / 'tmp/vercel-stage-path.txt').write_text(str(target), encoding='utf-8')
print(target)
