"""Build a portable Windows folder in staging, away from sources and user data."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(WORKSPACE / 'Outils'))
from chemins import local_root
from mpsi_desktop.google_oauth_config import (GOOGLE_OAUTH_ASSET,
    select_google_oauth_client, write_google_oauth_client)

REPOSITORY_PATTERN = re.compile(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9_.-]{1,100}\Z')
UPDATE_CHANNEL = 'update-channel.json'


def validate_repository(value):
    if (not isinstance(value, str) or not REPOSITORY_PATTERN.fullmatch(value)
            or value.split('/')[1] in {'.', '..'} or value.endswith('.git')):
        raise ValueError('Le dépôt de mises à jour doit respecter propriétaire/dépôt (GitHub public), sans URL ni jeton.')
    return value


def stage_assets(source, destination, repository=None, google_oauth_client=None, require_google_drive=False):
    """Inject public release identity into a copy, never into the source assets."""
    source, destination = Path(source), Path(destination)
    selected = validate_repository(repository) if repository is not None else None
    google = select_google_oauth_client(source, google_oauth_client, require_google_drive)
    channel = source / UPDATE_CHANNEL
    if repository is None and channel.exists():
        if channel.is_symlink() or not channel.is_file() or channel.stat().st_size > 4096:
            raise ValueError('La configuration publique des mises à jour est invalide.')
        try:
            content = json.loads(channel.read_text(encoding='utf-8-sig'))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError('La configuration publique des mises à jour doit être un JSON valide.') from exc
        if not isinstance(content, dict) or set(content) != {'repository'}:
            raise ValueError('La configuration publique des mises à jour accepte uniquement repository, sans jeton.')
        selected = validate_repository(content['repository'])
    if source.is_symlink() or source.resolve() != source:
        raise ValueError('Le dossier des ressources ne doit pas être un lien.')
    for parent, directories, names in os.walk(source, followlinks=False):
        for name in directories + names:
            candidate = Path(parent) / name
            if candidate.is_symlink() or candidate.resolve() != candidate:
                raise ValueError('Une ressource de construction ne doit pas être un lien.')
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(UPDATE_CHANNEL, GOOGLE_OAUTH_ASSET))
    if selected is not None:
        (destination / UPDATE_CHANNEL).write_text(json.dumps({'repository': selected}) + '\n', encoding='utf-8')
    write_google_oauth_client(destination, google)
    return destination


def _overlaps(left, right):
    return left == right or left.is_relative_to(right) or right.is_relative_to(left)


def validate_output(value, *, source=ROOT, workspace=WORKSPACE):
    source, workspace = Path(source).resolve(), Path(workspace).resolve()
    output = Path(value).expanduser()
    if not output.is_absolute():
        output = workspace / output
    output = output.resolve()
    target = output / 'PrepaPilot'
    active = workspace / 'Application' / 'PrepaPilot'
    delivery = local_root(workspace) / 'Livraison'
    if not output.is_relative_to(workspace) and (output != delivery or delivery.resolve() != delivery):
        raise ValueError('Choisis le dossier local Livraison ou un dossier de sortie dans le projet PrépaPilot.')
    if _overlaps(output, source) or _overlaps(target, source):
        raise ValueError('Le dossier de construction doit être séparé des sources, sans les contenir.')
    if _overlaps(output, active) or _overlaps(target, active):
        raise ValueError('Construis dans le dossier local Livraison, séparé de l’application actuelle et de ses données.')
    if target.resolve() != target:
        raise ValueError('Le dossier de sortie ne doit pas rediriger vers un autre emplacement.')
    if (target / 'data').exists():
        raise ValueError('Le dossier de sortie contient des données. Choisis un autre dossier.')
    return output


def main():
    parser = argparse.ArgumentParser(description='Construire PrépaPilot sans écraser la version utilisée.')
    parser.add_argument('--output', default=str(local_root(WORKSPACE) / 'Livraison'), help='Dossier de distribution : Livraison dans les fichiers locaux par défaut, ou un dossier du projet. Le sous-dossier PrepaPilot y sera créé.')
    parser.add_argument('--repository', help='Dépôt public GitHub propriétaire/dépôt utilisé pour les mises à jour, sans URL ni jeton.')
    parser.add_argument('--google-oauth-client', type=Path, help='JSON du client OAuth de bureau commun à intégrer, sans connexion personnelle.')
    parser.add_argument('--require-google-drive', action='store_true', help='Refuser la construction sans client OAuth Google commun valide.')
    options = parser.parse_args()
    try:
        output = validate_output(options.output)
        if options.repository is not None:
            validate_repository(options.repository)
        select_google_oauth_client(ROOT / 'assets', options.google_oauth_client, options.require_google_drive)
    except ValueError as exc:
        parser.error(str(exc))
    work = local_root(WORKSPACE) / 'Construction'
    if work.resolve() != work:
        parser.error('Le dossier local de construction ne doit pas rediriger vers un autre emplacement.')
    work.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed', '--onedir',
            '--name', 'PrepaPilot', '--distpath', str(output), '--workpath', str(work),
            '--specpath', str(work), '--paths', str(ROOT), '--icon', str(ROOT / 'assets/app.ico'),
            '--add-data', f'{ROOT / "licenses"};licenses',
            '--add-data', f'{ROOT / "README.md"};.']
    for name in ['telegram', 'matplotlib', 'numpy', 'pandas', 'scipy', 'tkinter', 'pytest', 'IPython', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets']:
        args.extend(['--exclude-module', name])
    for name in ['mpsi_desktop.i18n', 'mpsi_desktop.language_choice',
                 'mpsi_desktop.translations_shell', 'mpsi_desktop.translations_study',
                 'mpsi_desktop.translations_schedule', 'mpsi_desktop.translations_progress',
                 'mpsi_desktop.translations_cloud', 'mpsi_desktop.translations_updates',
                 'mpsi_desktop.translations_experience', 'mpsi_desktop.translations_engagement',
                 'mpsi_desktop.translations_quick_actions', 'mpsi_desktop.translations_search',
                 'mpsi_desktop.translations_focus_bar', 'mpsi_desktop.translations_help',
                 'mpsi_desktop.translations_launch', 'mpsi_desktop.translations_organization']:
        args.extend(['--hidden-import', name])
    args.append(str(ROOT / 'lancer.py'))
    # Exclude unrelated ICU/OpenSSL DLLs from the packaging search path.
    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    system = Path(env.get('SystemRoot', 'C:/Windows'))
    env['PATH'] = os.pathsep.join([str(Path(sys.executable).parent), str(Path(sys.base_prefix)), str(system / 'System32'), str(system)])
    with tempfile.TemporaryDirectory(prefix='resources-', dir=work) as staging:
        try:
            assets = stage_assets(ROOT / 'assets', Path(staging) / 'assets', options.repository,
                                  options.google_oauth_client, options.require_google_drive)
        except ValueError as exc:
            parser.error(str(exc))
        args[-1:-1] = ['--add-data', f'{assets};assets']
        subprocess.run(args, cwd=ROOT, env=env, check=True)
    print(output / 'PrepaPilot' / 'PrepaPilot.exe')


if __name__ == '__main__':
    main()
