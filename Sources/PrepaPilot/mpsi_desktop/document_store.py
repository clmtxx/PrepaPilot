"""Portable originals and their metadata. No parsing, generation or network calls."""
from __future__ import annotations

from contextlib import suppress
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import unicodedata
import uuid

from .i18n import tr

from .catalog import DOCUMENT_KINDS


ALLOWED_EXTENSIONS = frozenset({
    '.pdf', '.txt', '.md', '.docx', '.pptx', '.xlsx', '.odt', '.ods', '.odp',
    '.csv', '.rtf', '.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tif', '.tiff', '.tex',
})

ALL_DOCUMENT_FOLDERS = object()
MAX_DOCUMENT_FOLDERS = 1000


def normalize_document_folder_name(name):
    """A display label, never a filesystem path."""
    if not isinstance(name, str):
        raise ValueError(tr('Donne un nom au dossier.'))
    if any(unicodedata.category(character).startswith('C') or
           unicodedata.category(character) in {'Zl', 'Zp'} for character in name):
        raise ValueError(tr('Le nom du dossier ne peut pas contenir de caractères de contrôle.'))
    name = unicodedata.normalize('NFC', name).strip()
    if not 1 <= len(name) <= 100:
        raise ValueError(tr('Le nom du dossier doit contenir entre 1 et 100 caractères.'))
    return name


def _folder_identity(identity):
    if type(identity) is not int or not 1 <= identity <= 2**63 - 1:
        raise ValueError(tr('Choisis un dossier valide.'))
    return identity


class DocumentStoreMixin:
    @property
    def document_directory(self):
        return Path(self.path).resolve().parent / 'documents'

    def init_document_tables(self):
        with self._lock, self._connection:
            self._connection.execute('''CREATE TABLE IF NOT EXISTS document_folders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )''')
            self._connection.execute('''CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                subject TEXT NOT NULL,
                kind TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_path TEXT NOT NULL UNIQUE,
                size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                legacy_summary_id INTEGER UNIQUE,
                folder_id INTEGER
            )''')
            if 'folder_id' not in {row['name'] for row in self._connection.execute('PRAGMA table_info(documents)')}:
                self._connection.execute('ALTER TABLE documents ADD COLUMN folder_id INTEGER')
            self._connection.execute('CREATE INDEX IF NOT EXISTS documents_subject_kind ON documents(subject, kind)')
            self._connection.execute('CREATE INDEX IF NOT EXISTS documents_folder ON documents(folder_id)')
        self.document_directory.mkdir(parents=True, exist_ok=True)
        if self._rows("SELECT name FROM sqlite_master WHERE type='table' AND name='summaries'"):
            # Keep a durable migration marker even when a migrated document is deleted.
            with self._lock, self._connection:
                self._connection.execute('CREATE TABLE IF NOT EXISTS document_migrations (summary_id INTEGER PRIMARY KEY)')
            for row in self._rows('''SELECT s.* FROM summaries s
                    WHERE NOT EXISTS (SELECT 1 FROM document_migrations m WHERE m.summary_id=s.id)
                    AND NOT EXISTS (SELECT 1 FROM documents d WHERE d.legacy_summary_id=s.id)'''):
                self._persist_documents([dict(
                    source=None, content=row['text'].encode('utf-8'), title=row['title'].strip() or tr('Ancienne fiche'),
                    subject='autre', kind='cours', original_name=f"ancienne-fiche-{row['id']}.txt",
                    description=tr('Fiche conservée de l’ancienne application. Le fichier source original n’était pas enregistré.'),
                    legacy_summary_id=row['id'],
                )])

    def list_document_folders(self):
        rows = self._rows('''SELECT f.*, COUNT(d.id) AS document_count
                            FROM document_folders f LEFT JOIN documents d ON d.folder_id=f.id
                            GROUP BY f.id''')
        return sorted(rows, key=lambda row: (row['name'].casefold(), row['id']))

    def get_document_folder(self, identity):
        rows = self._rows('SELECT * FROM document_folders WHERE id=?', (_folder_identity(identity),))
        return rows[0] if rows else None

    def _validate_document_folder(self, identity):
        if identity is not None and self.get_document_folder(identity) is None:
            raise ValueError(tr('Ce dossier n’existe plus. Choisis un autre dossier.'))
        return identity

    def _unique_document_folder_name(self, name, *, excluding=None):
        name = normalize_document_folder_name(name)
        if any(row['id'] != excluding and unicodedata.normalize('NFC', row['name']).casefold() == name.casefold()
               for row in self._rows('SELECT id,name FROM document_folders')):
            raise ValueError(tr('Un dossier porte déjà ce nom.'))
        return name

    def create_document_folder(self, name):
        with self._lock, self._connection:
            self._connection.execute('BEGIN IMMEDIATE')
            name = self._unique_document_folder_name(name)
            if self._connection.execute('SELECT COUNT(*) FROM document_folders').fetchone()[0] >= MAX_DOCUMENT_FOLDERS:
                raise ValueError(tr('La bibliothèque peut contenir au maximum 1 000 dossiers.'))
            cursor = self._connection.execute('INSERT INTO document_folders(name) VALUES (?)', (name,))
            return int(cursor.lastrowid)

    def rename_document_folder(self, identity, name):
        identity = _folder_identity(identity)
        with self._lock, self._connection:
            self._connection.execute('BEGIN IMMEDIATE')
            if self.get_document_folder(identity) is None:
                return False
            name = self._unique_document_folder_name(name, excluding=identity)
            self._connection.execute('UPDATE document_folders SET name=? WHERE id=?', (name, identity))
            return True

    def delete_document_folder(self, identity):
        identity = _folder_identity(identity)
        with self._lock, self._connection:
            self._connection.execute('BEGIN IMMEDIATE')
            if self.get_document_folder(identity) is None:
                return False
            self._connection.execute('''UPDATE documents SET folder_id=NULL,updated_at=CURRENT_TIMESTAMP
                                        WHERE folder_id=?''', (identity,))
            self._connection.execute('DELETE FROM document_folders WHERE id=?', (identity,))
            return True

    def move_documents(self, identities, folder_id):
        identities = list(identities)
        if any(type(identity) is not int or not 1 <= identity <= 2**63 - 1 for identity in identities):
            raise ValueError(tr('Choisis des documents valides.'))
        identities = list(dict.fromkeys(identities))
        with self._lock, self._connection:
            self._connection.execute('BEGIN IMMEDIATE')
            self._validate_document_folder(folder_id)
            if any(self.get_document(identity) is None for identity in identities):
                raise ValueError(tr('Un document n’existe plus. Actualise la bibliothèque.'))
            self._connection.executemany('''UPDATE documents SET folder_id=?,updated_at=CURRENT_TIMESTAMP
                                           WHERE id=?''', ((folder_id, identity) for identity in identities))
            return len(identities)

    def _document_metadata(self, title, subject, kind, description, *, retained_subject=None):
        if not isinstance(title, str) or not title.strip():
            raise ValueError(tr('Donne un titre au document.'))
        if len(title.strip()) > 240:
            raise ValueError(tr('Le titre est limité à 240 caractères.'))
        subjects = self.subject_labels(include_archived=False)
        if retained_subject in self.subject_labels(include_archived=True):
            subjects[retained_subject] = self.subject_labels(include_archived=True)[retained_subject]
        if subject not in subjects or kind not in DOCUMENT_KINDS:
            raise ValueError(tr('Choisis une matière et un type de document valides.'))
        if not isinstance(description, str) or len(description) > 10000:
            raise ValueError(tr('La description est limitée à 10 000 caractères.'))
        return title.strip(), subject, kind, description.strip()

    def import_documents(self, paths, subject, kind, *, description='', folder_id=None):
        self._validate_document_folder(folder_id)
        paths=list(paths)
        if not paths:
            raise ValueError(tr('Choisis au moins un document.'))
        specs=[]
        for source in paths:
            source=Path(source).expanduser().resolve()
            if not source.is_file():
                raise ValueError(tr('Le fichier « {name} » est introuvable.', name=source.name))
            if source.suffix.lower() not in ALLOWED_EXTENSIONS:
                raise ValueError(tr('Le format « {extension} » n’est pas pris en charge.', extension=source.suffix or tr("sans extension")))
            title,subject,kind,description=self._document_metadata(source.stem,subject,kind,description)
            specs.append(dict(source=source,title=title,subject=subject,kind=kind,
                              description=description,original_name=source.name,legacy_summary_id=None,folder_id=folder_id))
        return self._persist_documents(specs)

    def import_document(self, path, subject, kind, *, title=None, description='', folder_id=None):
        self._validate_document_folder(folder_id)
        source=Path(path).expanduser().resolve()
        if not source.is_file():
            raise ValueError(tr('Le fichier « {name} » est introuvable.', name=source.name))
        if source.suffix.lower() not in ALLOWED_EXTENSIONS:
            raise ValueError(tr('Ce format de fichier n’est pas pris en charge.'))
        title,subject,kind,description=self._document_metadata(source.stem if title is None else title,subject,kind,description)
        return self._persist_documents([dict(source=source,title=title,subject=subject,kind=kind,
            description=description,original_name=source.name,legacy_summary_id=None,folder_id=folder_id)])[0]

    def _persist_documents(self, specs):
        created=[]
        staged=[]
        identities=[]
        directory=self.document_directory
        directory.mkdir(parents=True,exist_ok=True)
        try:
            # Stage outside the managed directory: a concurrent archive only
            # sees committed originals, and UI reads need not wait for copying.
            for spec in specs:
                extension=Path(spec['original_name']).suffix.lower()
                target=directory/(uuid.uuid4().hex+extension)
                temporary=directory.parent/('.document-import-'+uuid.uuid4().hex+'.tmp')
                staged.append(temporary)
                if spec['source'] is None:
                    temporary.write_bytes(spec['content'])
                else:
                    shutil.copyfile(spec['source'],temporary)
                spec['target']=target
                spec['temporary']=temporary
                spec['size_bytes']=temporary.stat().st_size
            with self._lock:
                try:
                    with self._connection:
                        self._connection.execute('BEGIN IMMEDIATE')
                        for spec in specs:
                            if spec['legacy_summary_id'] is None:
                                # The catalogue may have changed while a large file was copied.
                                self._document_metadata(spec['title'], spec['subject'], spec['kind'], spec['description'])
                            self._validate_document_folder(spec.get('folder_id'))
                            spec['temporary'].replace(spec['target'])
                            created.append(spec['target'])
                            cursor=self._connection.execute('''INSERT INTO documents
                                (title,subject,kind,original_name,stored_path,size_bytes,description,legacy_summary_id,folder_id)
                                VALUES (?,?,?,?,?,?,?,?,?)''',(
                                    spec['title'],spec['subject'],spec['kind'],spec['original_name'],
                                    'documents/'+spec['target'].name,spec['size_bytes'],spec['description'],spec['legacy_summary_id'],
                                    spec.get('folder_id')))
                            identities.append(int(cursor.lastrowid))
                            if spec['legacy_summary_id'] is not None:
                                self._connection.execute('INSERT OR IGNORE INTO document_migrations(summary_id) VALUES (?)',
                                                         (spec['legacy_summary_id'],))
                except Exception:
                    for path in created:
                        with suppress(OSError):path.unlink(missing_ok=True)
                    raise
        finally:
            for path in staged:
                with suppress(OSError):path.unlink(missing_ok=True)
        return identities

    def list_documents(self, subject=None, kind=None, search='', *, folder_id=ALL_DOCUMENT_FOLDERS):
        clauses=[]
        parameters=[]
        for column,value in (('subject',subject),('kind',kind)):
            if value:
                clauses.append(column+'=?')
                parameters.append(value)
        if folder_id is None:
            clauses.append('folder_id IS NULL')
        elif folder_id is not ALL_DOCUMENT_FOLDERS:
            clauses.append('folder_id=?')
            parameters.append(_folder_identity(folder_id))
        sql='SELECT * FROM documents'+(' WHERE '+' AND '.join(clauses) if clauses else '')
        rows=self._rows(sql+' ORDER BY created_at DESC,id DESC',tuple(parameters))
        needle=str(search).strip().casefold()
        return [row for row in rows if not needle or needle in '\n'.join(
            str(row[key]) for key in ('title','original_name','description')).casefold()]

    def get_document(self, identity):
        rows=self._rows('SELECT * FROM documents WHERE id=?',(identity,))
        return rows[0] if rows else None

    def update_document(self, identity, title, subject, kind, description='', *, folder_id=ALL_DOCUMENT_FOLDERS):
        with self._lock, self._connection:
            self._connection.execute('BEGIN IMMEDIATE')
            previous = self.get_document(identity)
            if previous is None:
                return False
            values=self._document_metadata(title,subject,kind,description,retained_subject=previous['subject'])
            folder_id = previous['folder_id'] if folder_id is ALL_DOCUMENT_FOLDERS else folder_id
            self._validate_document_folder(folder_id)
            return self._connection.execute('''UPDATE documents SET title=?,subject=?,kind=?,description=?,folder_id=?,
                                updated_at=CURRENT_TIMESTAMP WHERE id=?''',values+(folder_id,identity)).rowcount > 0

    def _resolve_document_path(self, row, *, require_exists=True):
        raw=row['stored_path']
        if not isinstance(raw,str):
            raise ValueError(tr('Le chemin de ce document est invalide.'))
        relative=PurePosixPath(raw)
        if ('\\' in raw or relative.is_absolute() or PureWindowsPath(raw).is_absolute()
                or len(relative.parts)!=2 or relative.parts[0]!='documents'
                or '..' in relative.parts or ':' in raw or relative.suffix.lower() not in ALLOWED_EXTENSIONS):
            raise ValueError(tr('Le chemin de ce document est invalide.'))
        base=self.document_directory.resolve()
        path=(base/relative.name).resolve()
        if not path.is_relative_to(base) or path==base:
            raise ValueError(tr('Le document doit rester dans la bibliothèque.'))
        if require_exists and not path.is_file():
            raise ValueError(tr('Le fichier original est absent. Restaure une sauvegarde complète pour le retrouver.'))
        return path

    def document_path(self, identity):
        row=self.get_document(identity)
        if row is None:
            raise ValueError(tr('Ce document n’existe plus.'))
        return self._resolve_document_path(row)

    def export_document(self, identity, destination):
        source=self.document_path(identity)
        target=Path(destination).expanduser().resolve()
        if target==source or target.is_relative_to(self.document_directory.resolve()):
            raise ValueError(tr('Choisis un emplacement en dehors de la bibliothèque.'))
        if target.suffix.lower()!=source.suffix.lower():
            raise ValueError(tr('Conserve l’extension {extension} du fichier original.', extension=source.suffix))
        temporary=target.with_name('.'+target.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            shutil.copyfile(source,temporary)
            temporary.replace(target)
        finally:
            with suppress(OSError):temporary.unlink(missing_ok=True)
        return target

    def delete_document(self, identity):
        with self._lock:
            row=self.get_document(identity)
            if row is None:return False
            source=self._resolve_document_path(row,require_exists=False)
            temporary=source.with_name('.delete-'+uuid.uuid4().hex+'.tmp')
            moved=False
            try:
                if source.exists():
                    source.replace(temporary)
                    moved=True
                with self._connection:
                    self._connection.execute('DELETE FROM documents WHERE id=?',(identity,))
            except Exception:
                if moved:temporary.replace(source)
                raise
            if moved:temporary.unlink()
            return True
