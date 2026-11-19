"""Extract a requested file's added lines from a Git unified diff."""

import argparse
import ast
import hashlib
import io
import re
import sys
from pathlib import Path
from typing import List


HUNK_HEADER = re.compile(r'^@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@')
METADATA_KEYS = (
    'old mode', 'new mode', 'new file mode', 'deleted file mode',
    'copy from', 'copy to', 'rename from', 'rename to',
    'similarity index', 'dissimilarity index', 'index',
)
EMPTY_BLOBS = (
    hashlib.sha1(b'blob 0\0').hexdigest(),
    hashlib.sha256(b'blob 0\0').hexdigest(),
)
BINARY_LINE = re.compile(r'^[A-Za-z][0-9A-Za-z!#$%&()*+;<=>?@^_`{|}~\-]+\n?$')


def _unquote_path(path: str) -> str:
    if not path.startswith('"'):
        return path
    decoded = ast.literal_eval(path)
    # Git quotes non-ASCII paths as octal escapes for their UTF-8 bytes.
    return decoded.encode('latin-1').decode('utf-8')


def _text_header_path(header: str) -> str:
    path = header[4:].rstrip('\n')
    # Git separates an unquoted path containing spaces from the line ending with
    # one TAB. Literal tabs in filenames are quoted; keep filename spaces intact.
    if path.endswith('\t'):
        path = path[:-1]
    return _unquote_path(path)


def _binary_targets_file(header: str, metadata: dict, filename: str) -> bool:
    for key in ('rename to', 'copy to'):
        if key in metadata:
            return _unquote_path(metadata[key]) == filename
    if header == 'diff --git a/' + filename + ' b/' + filename:
        return True
    quoted = re.fullmatch(r'diff --git ("(?:[^"\\]|\\.)*") ("(?:[^"\\]|\\.)*")', header)
    return bool(quoted and _unquote_path(quoted.group(1)) == 'a/' + filename and
                _unquote_path(quoted.group(2)) == 'b/' + filename)


def _finish_file(state: str, metadata: dict, binary_chunks: int) -> None:
    if state in ('start', 'text-complete', 'binary-summary'):
        return
    if state == 'binary-header' and binary_chunks:
        return
    if state != 'metadata':
        raise ValueError('Incomplete diff file or hunk')

    complete_change = False
    for first, second in [('old mode', 'new mode'), ('rename from', 'rename to'),
                          ('copy from', 'copy to')]:
        if (first in metadata) != (second in metadata):
            raise ValueError('Incomplete diff metadata')
        if first in metadata:
            if first != 'old mode' and metadata.get('similarity index') != '100%':
                raise ValueError('Changed rename/copy is missing its diff content')
            complete_change = True

    for mode, empty_side, zero_side in [('new file mode', 1, 0), ('deleted file mode', 0, 1)]:
        if mode in metadata:
            hashes = metadata.get('index', '').split(' ')[0].split('..')
            if (len(hashes) != 2 or not hashes[zero_side] or
                    set(hashes[zero_side]) != {'0'} or not hashes[empty_side] or
                    not any(blob.startswith(hashes[empty_side]) for blob in EMPTY_BLOBS)):
                raise ValueError('Added/deleted file is missing its diff content')
            complete_change = True
    hashes = metadata.get('index', '').split(' ')[0].split('..')
    if len(hashes) == 2 and hashes[0] != hashes[1] and all(value.strip('0') for value in hashes):
        raise ValueError('Changed indexed content is missing its diff content')
    if not complete_change:
        raise ValueError('Diff file has no content or complete metadata change')


def extract_added_lines(diff: str, filename: str) -> List[str]:
    """Keep additions in filename's hunks, excluding metadata and other files."""
    additions = []
    selected = False
    state = 'start'
    file_header = ''
    metadata = {}
    binary_chunks = binary_lines = 0
    old_remaining = new_remaining = 0
    annotation_allowed = False

    # Git counts LF-terminated lines; Unicode separators, VT/FF and CR are content.
    for line in io.StringIO(diff, newline='\n'):
        if line.rstrip('\n') == '\\ No newline at end of file':
            if not annotation_allowed:
                raise ValueError('Unexpected no-newline annotation')
            annotation_allowed = False
            continue
        if state == 'hunk':
            prefix = line[0]
            if prefix not in (' ', '+', '-'):
                raise ValueError('Incomplete or malformed diff hunk')
            if prefix != '+':
                old_remaining -= 1
            if prefix != '-':
                new_remaining -= 1
            if old_remaining < 0 or new_remaining < 0:
                raise ValueError('Diff hunk line counts do not match')
            if selected and prefix == '+':
                additions.append(line[1:])
            annotation_allowed = True
            if old_remaining == new_remaining == 0:
                state = 'text-complete'
            continue

        if line.startswith('diff --git '):
            _finish_file(state, metadata, binary_chunks)
            selected = False
            state = 'metadata'
            file_header = line.rstrip('\n')
            metadata = {}
            binary_chunks = binary_lines = 0
            annotation_allowed = False
            continue

        if state == 'old-header':
            if not line.startswith('+++ '):
                raise ValueError('Missing new-file header')
            path = _text_header_path(line)
            if path != '/dev/null' and not path.startswith('b/'):
                raise ValueError('Invalid new-file path')
            selected = path == 'b/' + filename
            state = 'text-headers'
        elif state in ('text-headers', 'text-complete'):
            match = HUNK_HEADER.match(line)
            if not match:
                raise ValueError('Expected a hunk header; orphan diff content is not allowed')
            old_remaining = int(match.group(1) or 1)
            new_remaining = int(match.group(2) or 1)
            if old_remaining == new_remaining == 0:
                raise ValueError('Empty diff hunk')
            state = 'hunk'
            annotation_allowed = False
        elif state == 'metadata':
            if line.startswith('--- '):
                path = _text_header_path(line)
                if path != '/dev/null' and not path.startswith('a/'):
                    raise ValueError('Invalid old-file path')
                state = 'old-header'
            elif ((line.startswith('Binary files ') and line.rstrip('\n').endswith(' differ')) or
                  line == 'GIT binary patch\n'):
                if _binary_targets_file(file_header, metadata, filename):
                    raise ValueError('Cannot extract added links from a binary target file')
                state = 'binary-header' if line == 'GIT binary patch\n' else 'binary-summary'
            else:
                key = next((key for key in METADATA_KEYS if line.startswith(key + ' ')), None)
                if key is None or key in metadata:
                    raise ValueError('Unexpected or duplicate diff metadata')
                metadata[key] = line[len(key) + 1:].rstrip('\n')
        elif state == 'binary-header':
            if not re.fullmatch(r'(?:literal|delta) \d+\n?', line):
                raise ValueError('Expected a binary patch header')
            state = 'binary-body'
            binary_lines = 0
        elif state == 'binary-body':
            if line == '\n' and binary_lines:
                binary_chunks += 1
                state = 'binary-header'
            elif BINARY_LINE.fullmatch(line):
                binary_lines += 1
            else:
                raise ValueError('Malformed binary patch data')
        else:
            raise ValueError('Expected a Git file header')

    _finish_file(state, metadata, binary_chunks)
    return additions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('diff_file')
    parser.add_argument('filename')
    args = parser.parse_args()
    try:
        filename = Path(args.filename).resolve().relative_to(Path.cwd().resolve())
        # Preserve CRLF and unrelated non-UTF-8 bytes until additions are selected.
        with open(args.diff_file, encoding='utf-8', errors='surrogateescape', newline='') as source:
            diff = source.read()
        additions = ''.join(extract_added_lines(diff, filename.as_posix()))
        # Validate all selected output before emitting any bytes.
        sys.stdout.buffer.write(additions.encode('utf-8'))
    except (ValueError, SyntaxError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    main()
